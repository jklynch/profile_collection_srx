from collections import deque

from event_model import compose_resource
from ophyd import Cpt, Signal

from nslsii.areadetector.xspress3 import (
    build_detector_class
)


class FlyingCeXspress3FileReference(Signal):
    # this PV-lookalike tells databroker what the Xspress3
    #   image data looks like

    def __init__(self, *args, image_shape, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_shape = image_shape
        self.num_images = None

    def stage(self):
        # take this opportunity to read the number of images
        #  for the upcoming acquisition
        self.num_images = self.parent.cam.num_images.get()
        print(f"FlyingCeXspress3FileReference.stage num_images={self.num_images}")

    def describe(self):
        resource_document = super().describe()
        resource_document[self.name].update(
            {
                "external": "FILESTORE:",
                "dtype": "array",
                "shape": (self.num_images, *image_shape),
                "source": self.prefix,
            )
        )
        print(f"FlyingCeXspress3FileReference.describe: {resource_document}")
        return resource_document


EightChannelXspress3 = build_detector_class(
    channel_numbers=(1, 2, 3, 4, 5, 6, 7, 8),
    mcaroi_numbers=(1, 2, 3, 4)
)


class FlyingCeEightChannelXspress3(EightChannelXspress3):
    image_proxy = Cpt(FlyingCeXspress3FileReference, image_shape=(3, 4096))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._resource_document = None
        self._datum_factory = None
        self._asset_docs_cache = deque()

        self._resource_root = Path("/")
        self._resource_path = Path("tmp")

    def stage(self):
        self.stage()
        print("FlyingCeEightChannelXspress3.stage")

        self._resource_document, self._datum_factory, _ = compose_resource(
            start={"uid": "this will be removed on the next line"},
            spec="???",
            root=str(self._resource_root),
            resource_path=str(self._resource_path),
            resource_kwargs={"image_shape": self.image_proxy.shape}
        )
        self._resource_document.pop("run_start")
        self._asset_docs_cache.append(("resource", self._resource_document))

        return [self]

    def collect_asset_docs(self):
        print("FlyingCeEightChannelXspress3.collect_asset_docs()")
        documents = list(self._asset_docs_cache)
        self._asset_docs_cache.clear()
        for document in documents:
            yield document


cexs = FlyingCeEightChannelXspress3("XF:05IDD-ES{Xsp:3}:det1:", name="cexs")

