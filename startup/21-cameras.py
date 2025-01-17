print(f'Loading {__file__}...')


import sys
from ophyd.areadetector import (AreaDetector, ImagePlugin,
                                TIFFPlugin, StatsPlugin,
                                ROIPlugin, TransformPlugin,
                                OverlayPlugin, ProcessPlugin)
from ophyd.areadetector.plugins import PvaPlugin
from ophyd.areadetector.filestore_mixins import (FileStoreIterativeWrite,
                                                 FileStoreTIFF)
from ophyd.areadetector.trigger_mixins import SingleTrigger
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.device import Component as Cpt

from ophyd.areadetector.plugins import (ImagePlugin_V33, TIFFPlugin_V33,
                                        ROIPlugin_V33, StatsPlugin_V33)


class SRXTIFFPlugin(TIFFPlugin,
                    FileStoreTIFF,
                    FileStoreIterativeWrite):
    ...


class SRXAreaDetectorCam(AreaDetectorCam):
    pool_max_buffers = None


class SRXCamera(SingleTrigger, AreaDetector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_attrs = ['stats5']
        self.stats5.read_attrs = ['total']
        self.tiff.write_path_template=f'/nsls2/data/srx/assets/{self.name}/%Y/%m/%d/'
        self.tiff.read_path_template=f'/nsls2/data/srx/assets/{self.name}/%Y/%m/%d/'
        self.tiff.reg_root=f'/nsls2/data/srx/assets/{self.name}'

    cam = Cpt(AreaDetectorCam, 'cam1:')
    image = Cpt(ImagePlugin, 'image1:')
    pva = Cpt(PvaPlugin, 'Pva1:')  # Not really implemented in ophyd
    proc = Cpt(ProcessPlugin, 'Proc1:')
    over = Cpt(OverlayPlugin, 'Over1:')
    trans = Cpt(TransformPlugin, 'Trans1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')
    tiff = Cpt(SRXTIFFPlugin, 'TIFF1:',
               write_path_template='%Y/%m/%d/',
               read_path_template='%Y/%m/%d/',
               root='')

class SRXHackCamera(SingleTrigger, AreaDetector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_attrs = ['stats5']
        self.stats5.read_attrs = ['total']
        self.tiff.write_path_template=f'/nsls2/xf05id1/experiments/2021_cycle3/308253_Yang/camd01/%Y/%m/%d/'
        self.tiff.read_path_template=f'/nsls2/xf05id1/experiments/2021_cycle3/308253_Yang/camd01/%Y/%m/%d/'
        self.tiff.reg_root=f'/nsls2/xf05id1/experiments/2021_cycle3/308253_Yang/camd01/'

    cam = Cpt(AreaDetectorCam, 'cam1:')
    image = Cpt(ImagePlugin, 'image1:')
    pva = Cpt(PvaPlugin, 'Pva1:')  # Not really implemented in ophyd
    proc = Cpt(ProcessPlugin, 'Proc1:')
    over = Cpt(OverlayPlugin, 'Over1:')
    trans = Cpt(TransformPlugin, 'Trans1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')
    tiff = Cpt(SRXTIFFPlugin, 'TIFF1:',
               write_path_template='%Y/%m/%d/',
               read_path_template='%Y/%m/%d/',
               root='')

def create_camera(pv, name):
    try:
        cam = SRXCamera(pv, name=name)
    except TimeoutError:
        print(f'\nCannot connect to {name}. Continuing without device.\n')
        cam = None
    except Exception as ex:
        print(ex, end='\n\n')
        cam = None
    return cam

hfm_cam = create_camera('XF:05IDA-BI:1{FS:1-Cam:1}', 'hfm_cam')
bpmA_cam = create_camera('XF:05IDA-BI:1{BPM:1-Cam:1}', 'bpmA_cam')
nano_vlm = create_camera('XF:05ID1-ES{PG-Cam:1}', 'nano_vlm')
# hfvlm_AD = create_camera('XF:05IDD-BI:1{Mscp:1-Cam:1}', 'hfvlmAD')
hfvlm_AD = SRXHackCamera('XF:05IDD-BI:1{Mscp:1-Cam:1}', name='hfvlmAD')
if hfvlm_AD is not None:
    hfvlm_AD.read_attrs = ['tiff', 'stats1', 'stats2', 'stats3', 'stats4']
    hfvlm_AD.tiff.read_attrs = []
cam05 = create_camera('XF:05IDD-BI:1{Cam:5}', 'cam05')

