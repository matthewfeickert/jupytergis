from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pycrdt import Array, Doc, Map
from pydantic import BaseModel
from ypywidgets.comm import CommWidget

from uuid import uuid4

from .utils import normalize_path, get_source_layer_names

from .objects import (
    LayerType,
    SourceType,
    IHillshadeLayer,
    IImageLayer,
    IRasterLayer,
    IRasterSource,
    IVectorTileSource,
    IVectorLayer,
    IVectorTileLayer,
    IGeoJSONSource,
    IImageSource,
    IVideoSource,
    IWebGlLayer
)

logger = logging.getLogger(__file__)


class GISDocument(CommWidget):
    """
    Create a new GISDocument object.

    :param path: the path to the file that you would like to open.
    If not provided, a new empty document will be created.
    """

    def __init__(
        self,
        path: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        zoom: Optional[float] = None,
        extent: Optional[List[float]] = None,
        bearing: Optional[float] = None,
        pitch: Optional[float] = None,
        projection: Optional[str] = None
    ):
        comm_metadata = GISDocument._path_to_comm(path)

        ydoc = Doc()

        super().__init__(
            comm_metadata=dict(ymodel_name="@jupytergis:widget", **comm_metadata),
            ydoc=ydoc,
        )

        self.ydoc["layers"] = self._layers = Map()
        self.ydoc["sources"] = self._sources = Map()
        self.ydoc["options"] = self._options = Map()
        self.ydoc["layerTree"] = self._layerTree = Array()

        if path is None:
            if latitude is not None:
                self._options["latitude"] = latitude
            if longitude is not None:
                self._options["longitude"] = longitude
            if extent is not None:
                self._options["extent"] = extent
            if zoom is not None:
                self._options["zoom"] = zoom
            if bearing is not None:
                self._options["bearing"] = bearing
            if pitch is not None:
                self._options["pitch"] = pitch
            if projection is not None:
                self._options['projection'] = projection

    @property
    def layers(self) -> Dict:
        """
        Get the layer list
        """
        return self._layers.to_py()

    @property
    def layer_tree(self) -> List[str | Dict]:
        """
        Get the layer tree
        """
        return self._layerTree.to_py()

    def add_raster_layer(
        self,
        url: str,
        name: str = "Raster Layer",
        attribution: str = "",
        opacity: float = 1,
    ):
        """
        Add a Raster Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param url: The tiles url.
        :param attribution: The attribution.
        :param opacity: The opacity, between 0 and 1.
        """
        source = {
            "type": SourceType.RasterSource,
            "name": f"{name} Source",
            "parameters": {
                "url": url,
                "minZoom": 0,
                "maxZoom": 24,
                "attribution": attribution,
                "htmlAttribution": attribution,
                "provider": "",
                "bounds": [],
                "urlParameters": {},
            },
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.RasterLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id, "opacity": opacity},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_vectortile_layer(
        self,
        url: str,
        name: str = "Vector Tile Layer",
        source_layer: str | None = None,
        attribution: str = "",
        min_zoom: int = 0,
        max_zoom: int = 24,
        type: Literal["circle", "fill", "line"] = "line",
        color: str = "#FF0000",
        opacity: float = 1,
        logical_op:str | None = None,
        feature:str | None = None,
        operator:str | None = None,
        value:Union[str, float, float] | None = None
    ):

        """
        Add a Vector Tile Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param url: The tiles url.
        :param source_layer: The source layer to use.
        :param attribution: The attribution.
        :param opacity: The opacity, between 0 and 1.
        """
        source_layers = get_source_layer_names(url)
        if source_layer is None and len(source_layers) == 1:
            source_layer = source_layers[0]
        if source_layer not in source_layers:
            raise ValueError(f'source_layer should be one of {source_layers}')

        source = {
            "type": SourceType.VectorTileSource,
            "name": f"{name} Source",
            "parameters": {
                "url": url,
                "minZoom": min_zoom,
                "maxZoom": max_zoom,
                "attribution": attribution,
                "htmlAttribution": attribution,
                "provider": "",
                "bounds": [],
                "urlParameters": {},
            },
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.VectorTileLayer,
            "name": name,
            "visible": True,
            "parameters": {
                "source": source_id,
                "type": type,
                "opacity": opacity,
                "sourceLayer": source_layer,
                "color": color,
                "opacity": opacity,
            },
            "filters": {
                "appliedFilters": [
                    {
                        "feature": feature,
                        "operator": operator,
                        "value": value
                    }
                ],
                "logicalOp": logical_op
                }
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_geojson_layer(
        self,
        path: str | None = None,
        data: Dict | None = None,
        name: str = "GeoJSON Layer",
        type: "circle" | "fill" | "line" = "line",
        color: str = "#FF0000",
        opacity: float = 1,
        logical_op:str | None = None,
        feature:str | None = None,
        operator:str | None = None,
        value:Union[str, number, float] | None = None
    ):
        """
        Add a GeoJSON Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param path: The path to the JSON file to embed into the jGIS file.
        :param data: The raw GeoJSON data to embed into the jGIS file.
        :param type: The type of the vector layer to create.
        :param color: The color to apply to features.
        :param opacity: The opacity, between 0 and 1.
        """
        if path is None and data is None:
            raise ValueError("Cannot create a GeoJSON layer without data")

        if path is not None and data is not None:
            raise ValueError("Cannot set GeoJSON layer data and path at the same time")

        if path is not None:
            # We cannot put the path to the file in the model
            # We don't know where the kernel runs/live
            # The front-end would have no way of finding the file reliably
            # TODO Support urls to JSON files, in that case, don't embed the data
            with open(path, "r") as fobj:
                parameters = {"data": json.loads(fobj.read())}

        if data is not None:
            parameters = {"data": data}

        source = {
            "type": SourceType.GeoJSONSource,
            "name": f"{name} Source",
            "parameters": parameters,
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.VectorLayer,
            "name": name,
            "visible": True,
            "parameters": {
                "source": source_id,
                "type": type,
                "color": color,
                "opacity": opacity,
            },
             "filters": {
                "appliedFilters": [
                    {
                        "feature": feature,
                        "operator": operator,
                        "value": value
                    }
                ],
                "logicalOp": logical_op
                }
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_image_layer(
        self,
        url: str,
        coordinates: [],
        name: str = "Image Layer",
        opacity: float = 1,
    ):
        """
        Add a Image Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param url: The image url.
        :param coordinates: Corners of image specified in longitude, latitude pairs.
        :param opacity: The opacity, between 0 and 1.
        """

        if url is None or coordinates is None:
            raise ValueError("URL and Coordinates are required")

        source = {
            "type": SourceType.ImageSource,
            "name": f"{name} Source",
            "parameters": {
                "url": url,
                "coordinates": coordinates
            },
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.RasterLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id, "opacity": opacity},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_video_layer(
        self,
        urls: [],
        name: str = "Image Layer",
        coordinates: [] = [],
        opacity: float = 1,
    ):
        """
        Add a Video Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param urls: URLs to video content in order of preferred format.
        :param coordinates: Corners of video specified in longitude, latitude pairs.
        :param opacity: The opacity, between 0 and 1.
        """

        if urls is None or coordinates is None:
            raise ValueError("URLs and Coordinates are required")

        source = {
            "type": SourceType.VideoSource,
            "name": f"{name} Source",
            "parameters": {
                "urls": urls,
                "coordinates": coordinates
            },
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.RasterLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id, "opacity": opacity},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_filter(self, layer_id: str, logical_op:str, feature:str, operator:str, value:Union[str, number, float]):
        """
        Add a filter to a layer

        :param str layer_id: The ID of the layer to filter
        :param str logical_op: The logical combination to apply to filters. Must be "any" or "all"
        :param str feature: The feature to be filtered on
        :param str operator: The operator used to compare the feature and value
        :param Union[str, number, float] value: The value to be filtered on
        """
        layer = self._layers.get(layer_id)

        # Check if the layer exists
        if layer is None:
            raise ValueError(f"No layer found with ID: {layer_id}")

        # Initialize filters if it doesn't exist
        if 'filters' not in layer:
            layer['filters'] = {
                'appliedFilters': [
                    {
                        'feature': feature,
                        'operator': operator,
                        'value': value
                    }
                ],
                'logicalOp': logical_op}

            self._layers[layer_id] = layer
            return

        # Add new filter
        filters = layer['filters']
        filters['appliedFilters'].append({'feature': feature, 'operator': operator, 'value': value})

        # update the logical operation
        filters['logicalOp'] = logical_op

        self._layers[layer_id] = layer

    def update_filter(self, layer_id: str, logical_op:str, feature:str, operator:str, value:Union[str, number, float]):
        """
        Update a filter applied to a layer

        :param str layer_id: The ID of the layer to filter
        :param str logical_op: The logical combination to apply to filters. Must be "any" or "all"
        :param str feature: The feature to update the value for
        :param str operator: The operator used to compare the feature and value
        :param Union[str, number, float] value: The new value to be filtered on
        """
        layer = self._layers.get(layer_id)

        # Check if the layer exists
        if layer is None:
            raise ValueError(f"No layer found with ID: {layer_id}")

        if 'filters' not in layer:
            raise ValueError(f"No filters applied to layer: {layer_id}")

        # Find the feature within the layer
        feature = next((f for f in layer['filters']['appliedFilters'] if f['feature'] == feature), None)
        if feature is None:
            raise ValueError(f"No feature found with ID: {feature} in layer: {layer_id}")
            return

        # Update the feature value
        feature['value'] = value

        # update the logical operation
        layer['filters']['logicalOp'] = logical_op

        self._layers[layer_id] = layer

    def clear_filters(self, layer_id: str):
        """
        Clear filters on a layer

        :param str layer_id: The ID of the layer to clear filters from
        """
        layer = self._layers.get(layer_id)

        # Check if the layer exists
        if layer is None:
            raise ValueError(f"No layer found with ID: {layer_id}")

        if 'filters' not in layer:
            raise ValueError(f"No filters applied to layer: {layer_id}")

        layer['filters']['appliedFilters'] = []
        self._layers[layer_id] = layer

    def _add_source(self, new_object: "JGISObject"):
        _id = str(uuid4())
        obj_dict = json.loads(new_object.json())
        self._sources[_id] = obj_dict
        return _id

    def _add_layer(self, new_object: "JGISObject"):
        _id = str(uuid4())
        obj_dict = json.loads(new_object.json())
        self._layers[_id] = obj_dict
        self._layerTree.append(_id)
        return _id

    @classmethod
    def _path_to_comm(cls, filePath: Optional[str]) -> Dict:
        path = None
        format = None
        contentType = None

        if filePath is not None:
            path = normalize_path(filePath)
            file_name = Path(path).name
            try:
                ext = file_name.split(".")[1].lower()
            except Exception:
                raise ValueError("Can not detect file extension!")
            if ext == "jgis":
                format = "text"
                contentType = "jgis"
            else:
                raise ValueError("File extension is not supported!")
        return dict(
            path=path, format=format, contentType=contentType, createydoc=path is None
        )


class JGISLayer(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    name: str
    type: LayerType
    visible: bool
    parameters: Union[
        IRasterLayer,
        IVectorLayer,
        IVectorTileLayer,
        IHillshadeLayer,
        IImageLayer,
        IWebGlLayer
    ]
    _parent = Optional[GISDocument]

    def __init__(__pydantic_self__, parent, **data: Any) -> None:  # noqa
        super().__init__(**data)
        __pydantic_self__._parent = parent


class JGISSource(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    name: str
    type: SourceType
    parameters: Union[
        IRasterSource,
        IVectorTileSource,
        IGeoJSONSource,
        IImageSource,
        IVideoSource
    ]
    _parent = Optional[GISDocument]

    def __init__(__pydantic_self__, parent, **data: Any) -> None:  # noqa
        super().__init__(**data)
        __pydantic_self__._parent = parent


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class ObjectFactoryManager(metaclass=SingletonMeta):
    def __init__(self):
        self._factories: Dict[str, type[BaseModel]] = {}

    def register_factory(self, shape_type: str, cls: type[BaseModel]) -> None:
        if shape_type not in self._factories:
            self._factories[shape_type] = cls

    def create_layer(
        self, data: Dict, parent: Optional[GISDocument] = None
    ) -> Optional[JGISLayer]:
        object_type = data.get("type", None)
        name: str = data.get("name", None)
        visible: str = data.get("visible", True)
        filters = data.get("filters", None)
        if object_type and object_type in self._factories:
            Model = self._factories[object_type]
            args = {}
            params = data["parameters"]
            for field in Model.__fields__:
                args[field] = params.get(field, None)
            obj_params = Model(**args)
            return JGISLayer(
                parent=parent,
                name=name,
                visible=visible,
                type=object_type,
                parameters=obj_params,
                filters=filters
            )

        return None

    def create_source(
        self, data: Dict, parent: Optional[GISDocument] = None
    ) -> Optional[JGISSource]:
        object_type = data.get("type", None)
        name: str = data.get("name", None)
        if object_type and object_type in self._factories:
            Model = self._factories[object_type]
            args = {}
            params = data["parameters"]
            for field in Model.__fields__:
                args[field] = params.get(field, None)
            obj_params = Model(**args)
            return JGISSource(
                parent=parent, name=name, type=object_type, parameters=obj_params
            )

        return None


OBJECT_FACTORY = ObjectFactoryManager()

OBJECT_FACTORY.register_factory(LayerType.RasterLayer, IRasterLayer)
OBJECT_FACTORY.register_factory(LayerType.VectorLayer, IVectorLayer)
OBJECT_FACTORY.register_factory(LayerType.VectorTileLayer, IVectorTileLayer)
OBJECT_FACTORY.register_factory(LayerType.HillshadeLayer, IHillshadeLayer)
OBJECT_FACTORY.register_factory(LayerType.WebGlLayer, IWebGlLayer)
OBJECT_FACTORY.register_factory(LayerType.ImageLayer, IImageLayer)

OBJECT_FACTORY.register_factory(SourceType.VectorTileSource, IVectorTileSource)
OBJECT_FACTORY.register_factory(SourceType.RasterSource, IRasterSource)
OBJECT_FACTORY.register_factory(SourceType.GeoJSONSource, IGeoJSONSource)
OBJECT_FACTORY.register_factory(SourceType.ImageSource, IImageSource)
OBJECT_FACTORY.register_factory(SourceType.VideoSource, IVideoSource)
