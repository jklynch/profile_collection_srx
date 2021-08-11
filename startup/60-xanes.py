print(f'Loading {__file__}...')

import itertools
import collections
from collections import deque

import numpy as np
import time as ttime
import matplotlib.pyplot as plt

import bluesky.plans as bp
from bluesky.plans import list_scan
from bluesky.plan_stubs import (mv, one_1d_step)
from bluesky.preprocessors import (finalize_wrapper, subs_wrapper)
from bluesky.utils import short_uid as _short_uid
from epics import PV
# from databroker import DataBroker as db
from databroker import get_events
from numpy.lib.stride_tricks import as_strided
from ophyd.status import SubscriptionStatus
from ophyd.sim import NullStatus


def xanes_textout(scan=-1, header=[], userheader={}, column=[], usercolumn={},
                  usercolumnname=[], output=True, filename_add='', filedir=None):
    '''
    scan: can be scan_id (integer) or uid (string). default = -1 (last scan run)
    header: a list of items that exist in the event data to be put into the header
    userheader: a dictionary defined by user to put into the hdeader
    column: a list of items that exist in the event data to be put into the column data
    output: print all header fileds. if output = False, only print the ones that were able to be written
            default = True

    '''
    if (filedir is None):
        filedir = userdatadir
    h = db[scan]
    # get events using fill=False so it does not look for the metadata in filestorage with reference (hdf5 here)
    events = list(get_events(h, fill=False, stream_name='primary'))

    if (filename_add is not ''):
        filename = 'scan_' + str(h.start['scan_id']) + '_' + filename_add
    else:
        filename = 'scan_' + str(h.start['scan_id'])

    f = open(filedir+filename, 'w')

    staticheader = '# XDI/1.0 MX/2.0\n' \
              + '# Beamline.name: ' + h.start['beamline_id'] + '\n' \
              + '# Facility.name: NSLS-II\n' \
              + '# Facility.ring_current:' + str(events[0]['data']['ring_current']) + '\n' \
              + '# Scan.start.uid: ' + h.start['uid'] + '\n' \
              + '# Scan.start.time: '+ str(h.start['time']) + '\n' \
              + '# Scan.start.ctime: ' + ttime.ctime(h.start['time']) + '\n' \
              + '# Mono.name: Si 111\n'

    f.write(staticheader)

    for item in header:
        if (item in events[0].data.keys()):
            f.write('# ' + item + ': ' + str(events[0]['data'][item]) + '\n')
            if (output is True):
                print(item + ' is written')
        else:
            print(item + ' is not in the scan')

    for key in userheader:
        f.write('# ' + key + ': ' + str(userheader[key]) + '\n')
        if (output is True):
            print(key + ' is written')

    for idx, item in enumerate(column):
        if (item in events[0].data.keys()):
            f.write('# Column.' + str(idx+1) + ': ' + item + '\n')

    f.write('# ')
    for item in column:
        if (item in events[0].data.keys()):
            f.write(str(item) + '\t')

    for item in usercolumnname:
        f.write(item + '\t')

    f.write('\n')
    f.flush()

    idx = 0
    for event in events:
        for item in column:
            if (item in events[0].data.keys()):
                f.write('{0:8.6g}  '.format(event['data'][item]))
        for item in usercolumnname:
            try:
                f.write('{0:8.6g}  '.format(usercolumn[item][idx]))
            except KeyError:
                idx += 1
                f.write('{0:8.6g}  '.format(usercolumn[item][idx]))
        idx = idx + 1
        f.write('\n')

    f.close()


def xanes_afterscan_plan(scanid, filename, roinum):
    # Custom header list
    headeritem = []
    # Load header for our scan
    h = db[scanid]

    # Construct basic header information
    userheaderitem = {}
    userheaderitem['uid'] = h.start['uid']
    userheaderitem['sample.name'] = h.start['scan']['sample_name']
    # userheaderitem['initial_sample_position.hf_stage.x'] = h.start['initial_sample_position']['hf_stage_x']
    # userheaderitem['initial_sample_position.hf_stage.y'] = h.start['initial_sample_position']['hf_stage_y']
    # userheaderitem['hfm.y'] = h.start['hfm']['y']
    # userheaderitem['hfm.bend'] = h.start['hfm']['bend']

    # Create columns for data file
    columnitem = ['energy_energy', 'energy_bragg', 'energy_c2_x']
    # Include I_M, I_0, and I_t from the SRS
    if ('sclr1' in h.start['detectors']):
        if 'sclr_i0' in h.table('primary').keys():
            columnitem = columnitem + ['sclr_im', 'sclr_i0', 'sclr_it']
        else:
            columnitem = columnitem + ['sclr1_mca3', 'sclr1_mca2', 'sclr1_mca4']

    else:
        raise KeyError("SRS not found in data!")
    # Include fluorescence data if present, allow multiple rois
    if ('xs' in h.start['detectors']):
        if (type(roinum) is not list):
            roinum = [roinum]
        for i in roinum:
            roi_name = 'roi{:02}'.format(i)
            roi_key = []
            roi_key.append(getattr(xs.channel1.rois, roi_name).value.name)
            roi_key.append(getattr(xs.channel2.rois, roi_name).value.name)
            roi_key.append(getattr(xs.channel3.rois, roi_name).value.name)
            roi_key.append(getattr(xs.channel4.rois, roi_name).value.name)

        [columnitem.append(roi) for roi in roi_key]
    if ('xs2' in h.start['detectors']):
        if (type(roinum) is not list):
            roinum = [roinum]
        for i in roinum:
            roi_name = 'roi{:02}'.format(i)
            roi_key = []
            roi_key.append(getattr(xs2.channel1.rois, roi_name).value.name)

        [columnitem.append(roi) for roi in roi_key]
    # Construct user convenience columns allowing prescaling of ion chamber, diode and
    # fluorescence detector data
    usercolumnitem = {}
    datatablenames = []

    if ('xs' in h.start['detectors']):
        datatablenames = datatablenames + [str(roi) for roi in roi_key]
    if ('xs2' in h.start['detectors']):
        datatablenames = datatablenames + [str(roi) for roi in roi_key]
    if ('sclr1' in  h.start['detectors']):
        if 'sclr_im' in h.table(stream_name='primary').keys():
            datatablenames = datatablenames + ['sclr_im', 'sclr_i0', 'sclr_it']
            datatable = h.table(stream_name='primary', fields=datatablenames)
            im_array = np.array(datatable['sclr_im'])
            i0_array = np.array(datatable['sclr_i0'])
            it_array = np.array(datatable['sclr_it'])
        else:
            datatablenames = datatablenames + ['sclr1_mca2', 'sclr1_mca3', 'sclr1_mca4']
            datatable = h.table(stream_name='primary', fields=datatablenames)
            im_array = np.array(datatable['sclr1_mca3'])
            i0_array = np.array(datatable['sclr1_mca2'])
            it_array = np.array(datatable['sclr1_mca4'])
    else:
        raise KeyError
    # Calculate sums for xspress3 channels of interest
    if ('xs' in h.start['detectors']):
        for i in roinum:
            roi_name = 'roi{:02}'.format(i)
            roisum = datatable[getattr(xs.channel1.rois, roi_name).value.name]
            roisum = roisum + datatable[getattr(xs.channel2.rois, roi_name).value.name]
            roisum = roisum + datatable[getattr(xs.channel3.rois, roi_name).value.name]
            roisum = roisum + datatable[getattr(xs.channel4.rois, roi_name).value.name]
            usercolumnitem['If-{:02}'.format(i)] = roisum
            usercolumnitem['If-{:02}'.format(i)].round(0)
    if ('xs2' in h.start['detectors']):
        for i in roinum:
            roi_name = 'roi{:02}'.format(i)
            roisum = datatable[getattr(xs2.channel1.rois, roi_name).value.name]
            usercolumnitem['If-{:02}'.format(i)] = roisum
            usercolumnitem['If-{:02}'.format(i)].round(0)

    xanes_textout(scan = scanid, header = headeritem,
                  userheader = userheaderitem, column = columnitem,
                  usercolumn = usercolumnitem,
                  usercolumnname = usercolumnitem.keys(),
                  output = False, filename_add = filename, filedir=userdatadir)


def xanes_plan(erange=[], estep=[], acqtime=1., samplename='', filename='',
               det_xs=xs, harmonic=1, detune=0, align=False, align_at=None,
               roinum=1, shutter=True, per_step=None):

    '''
    erange (list of floats): energy ranges for XANES in eV, e.g. erange = [7112-50, 7112-20, 7112+50, 7112+120]
    estep  (list of floats): energy step size for each energy range in eV, e.g. estep = [2, 1, 5]
    acqtime (float): acqusition time to be set for both xspress3 and preamplifier
    samplename (string): sample name to be saved in the scan metadata
    filename (string): filename to be added to the scan id as the text output filename

    det_xs (xs3 detector): the xs3 detector used for the measurement
    harmonic (odd integer): when set to 1, use the highest harmonic achievable automatically.
                                    when set to an odd integer, force the XANES scan to use that harmonic
    detune:  add this value to the gap of the undulator to reduce flux [keV]
    align:  perform peakup_fine before scan [bool]
    align_at:  energy at which to align, default is average of the first and last energy points
    roinum: select the roi to be used to calculate the XANES spectrum
    shutter:  instruct the scan to control the B shutter [bool]
    per_step:  use a custom function for each energy point
    '''

    # Make sure user provided correct input
    if (erange is []):
        raise AttributeError("An energy range must be provided in a list by means of the 'erange' keyword.")
    if (estep is []):
        raise AttributeError("A list of energy steps must be provided by means of the 'esteps' keyword.")
    if (not isinstance(erange,list)) or (not isinstance(estep,list)):
        raise TypeError("The keywords 'estep' and 'erange' must be lists.")
    if (len(erange)-len(estep) is not 1):
        raise ValueError("The 'erange' and 'estep' lists are inconsistent; " \
                         + 'c.f., erange = [7000, 7100, 7150, 7500], estep = [2, 0.5, 5] ')
    if (type(roinum) is not list):
        roinum = [roinum]
    if (detune is not 0):
        yield from abs_set(energy.detune, detune)

    # Record relevant meta data in the Start document, defined in 90-usersetup.py
    # Add user meta data
    scan_md = {}
    get_stock_md(scan_md)
    scan_md['sample'] = {'name' : samplename}
    scan_md['scaninfo'] = {'type' : 'XANES',
                           'ROI' : roinum,
                           'raster' : False,
                           'dwell' : acqtime}
    scan_md['scan_input'] = str(np.around(erange, 2)) + ', ' + str(np.around(estep, 2))

    # Convert erange and estep to numpy array
    ept = np.array([])
    erange = np.array(erange)
    estep = np.array(estep)
    # Calculation for the energy points
    for i in range(len(estep)):
        ept = np.append(ept, np.arange(erange[i], erange[i+1], estep[i]))
    ept = np.append(ept, np.array(erange[-1]))

    # Record relevant meta data in the Start document, defined in 90-usersetup.py
    # Add user meta data
    scan_md = {}
    get_stock_md(scan_md)
    scan_md['scan']['sample_name'] = samplename
    scan_md['scan']['type'] = 'XAS_STEP'
    scan_md['scan']['ROI'] = roinum
    scan_md['scan']['dwell'] = acqtime
    # scan_md['scaninfo'] = {'type' : 'XANES',
    #                        'ROI' : roinum,
    #                        'raster' : False,
    #                        'dwell' : acqtime}
    scan_md['scan']['scan_input'] = str(np.around(erange, 2)) + ', ' + str(np.around(estep, 2))
    scan_md['scan']['energy'] = ept

    # Debugging, is this needed? is this recorded in scanoutput?
    # Convert energy to bragg angle
    egap = np.array(())
    ebragg = np.array(())
    exgap = np.array(())
    for i in ept:
        eg, eb, ex = energy.forward(i)
        egap = np.append(egap, eg)
        ebragg = np.append(ebragg, eb)
        exgap = np.append(exgap, ex)

    # Register the detectors
    det = [ring_current, sclr1, xbpm2, det_xs]
    # Setup xspress3
    yield from abs_set(det_xs.external_trig, False)
    yield from abs_set(det_xs.settings.acquire_time, acqtime)
    yield from abs_set(det_xs.total_points, len(ept))

    # Setup the scaler
    yield from abs_set(sclr1.preset_time, acqtime)

    # Setup DCM/energy options
    if (harmonic != 1):
        yield from abs_set(energy.harmonic, harmonic)

    # Prepare to peak up DCM at middle scan point
    if (align_at is not None):
        align = True
    if (align is True):
        if (align_at is None):
            align_at = 0.5*(ept[0] + ept[-1])
            print("Aligning at ", align_at)
            yield from abs_set(energy, align_at, wait=True)
        else:
            print("Aligning at ", align_at)
            yield from abs_set(energy, float(align_at), wait=True)

    # Peak up DCM at first scan point
    if (align is True):
        yield from peakup_fine(shutter=shutter)

    # Setup the live callbacks
    livecallbacks = []
    # Setup Raw data
    livetableitem = ['energy_energy', 'sclr_i0', 'sclr_it']
    roi_name = 'roi{:02}'.format(roinum[0])
    roi_key = []
    roi_key.append(getattr(det_xs.channel1.rois, roi_name).value.name)
    try:
        roi_key.append(getattr(det_xs.channel2.rois, roi_name).value.name)
        roi_key.append(getattr(det_xs.channel3.rois, roi_name).value.name)
        roi_key.append(getattr(det_xs.channel4.rois, roi_name).value.name)
    except NameError:
        pass
    livetableitem.append(roi_key[0])
    livecallbacks.append(LiveTable(livetableitem))
    liveploty = roi_key[0]
    liveplotx = energy.energy.name

    def my_factory(name):
        fig = plt.figure(num=name)
        ax = fig.gca()
        return fig, ax

    # liveplotfig = plt.figure('Raw XANES')
    # livecallbacks.append(LivePlot(liveploty, x=liveplotx, fig=liveplotfig))
    livecallbacks.append(HackLivePlot(liveploty, x=liveplotx,
                                      fig_factory=partial(my_factory, name='Raw XANES')))

    # Setup normalization
    liveploty = 'sclr_i0'
    i0 = 'sclr_i0'
    # liveplotfig2 = plt.figure('I0')
    # livecallbacks.append(LivePlot(liveploty, x=liveplotx, fig=liveplotfig2))
    livecallbacks.append(HackLivePlot(liveploty, x=liveplotx,
                                      fig_factory=partial(my_factory, name='I0')))

    # Setup normalized XANES
    # livenormfig = plt.figure('Normalized XANES')
    # livecallbacks.append(NormalizeLivePlot(roi_key[0], x=liveplotx, norm_key = i0, fig=livenormfig))
    livecallbacks.append(NormalizeLivePlot(roi_key[0], x=liveplotx, norm_key = i0,
                                           fig_factory=partial(my_factory, name='Normalized XANES')))


    def after_scan(name, doc):
        if (name != 'stop'):
            print("You must export this scan data manually: xanes_afterscan_plan(doc[-1], <filename>, <roinum>)")
            return
        xanes_afterscan_plan(doc['run_start'], filename, roinum)
        logscan_detailed('XAS_STEP')


    def at_scan(name, doc):
        scanrecord.current_scan.put(doc['uid'][:6])
        scanrecord.current_scan_id.put(str(doc['scan_id']))
        # Not sure if RE should be here, but not sure what to make it
        # scanrecord.current_type.put(RE.md['scaninfo']['type'])
        scanrecord.current_type.put(scan_md['scan']['type'])
        scanrecord.scanning.put(True)


    def finalize_scan():
        yield from abs_set(energy.move_c2_x, True)
        yield from abs_set(energy.harmonic, 1)
        # if (shutter is True):
        #     yield from mv(shut_b,'Close')
        yield from check_shutters(shutter, 'Close')
        if (detune is not None):
            yield from abs_set(energy.detune, 0)
        scanrecord.scanning.put(False)


    energy.move(ept[0])
    myscan = list_scan(det, energy, list(ept), per_step=per_step, md=scan_md)
    myscan = finalize_wrapper(myscan, finalize_scan)

    # Open b shutter
    # if (shutter is True):
    #     yield from mv(shut_b, 'Open')
    yield from check_shutters(shutter, 'Open')

    return (yield from subs_wrapper(myscan, {'all' : livecallbacks,
                                             'stop' : after_scan,
                                             'start' : at_scan}))


def xanes_batch_plan(xypos=[], erange=[], estep=[], acqtime=1.0,
                     waittime=10, peakup_N=2, peakup_E=None):
    """
    Setup a batch XANES scan at multiple points.
    This scan can also run peakup_fine() between points.

    xypos       <list>  A list of points to run XANES scans
    erange      <list>  A list of energy points to send to the XANES plan
    estep       <list>  A list of energy steps to send to the XANES plan
    acqtime     <float> Acquisition time for each data point.
    peakup_N    <int>   Run a peakup every peakup_N scans. Default is no peakup
    peakup_E    <float> The energy to run peakup at. Default is current energy

    """

    # Check positions
    if (xypos == []):
        print('You need to enter positions.')
        return

    # Check erange and estep
    if (erange == []):
        print('You need to enter erange.')
        return
    if (estep == []):
        print('You need to enter estep.')
        return

    # Get current energy and use it for peakup
    if (peakup_E == None):
        peakup_E = energy.position.energy

    # Convert keV to eV
    if (peakup_E < 1000):
        peakup_E = peakup_E * 1000

    # Loop through positions
    N = len(xypos)
    for i in range(N):
        print(f'Moving to:')
        print(f'\tx = {xypos[i][0]}')
        print(f'\ty = {xypos[i][1]}')
        hf_stage.x.move(xypos[i][0])
        hf_stage.y.move(xypos[i][1])
        if (len(xypos[i]) == 3):
            print(f'\tz = {xypos[i][2]}')
            hf_stage.z.move(xypos[i][2])

        # Move above edge and peak up
        if (i % peakup_N == 0):
            yield from mv(energy, peakup_E)
            yield from peakup_fine()

        # Run the energy scan
        yield from xanes_plan(erange=erange, estep=estep, acqtime=acqtime)

        # Wait
        if (i != (N-1)):
            print(f'Scan complete. Waiting {waittime} seconds...')
            bps.sleep(waittime)


def hfxanes_ioc(erange=[], estep=[], acqtime=1.0, samplename='', filename='',
                harmonic=1, detune=0, align=False, align_at=None,
                roinum=1, shutter=True, per_step=None, waittime=0):
    '''
    invokes hf2dxrf repeatedly with parameters provided separately.
        waittime                [sec]       time to wait between scans
        shutter                 [bool]      scan controls shutter
        align                   [bool]      optimize beam location on each scan
        roinum                  [1,2,3]     ROI number for data output

    '''

    scanlist = [ scanrecord.scan15, scanrecord.scan14, scanrecord.scan13,
                 scanrecord.scan12, scanrecord.scan11, scanrecord.scan10,
                 scanrecord.scan9, scanrecord.scan8, scanrecord.scan7,
                 scanrecord.scan6, scanrecord.scan5, scanrecord.scan4,
                 scanrecord.scan3, scanrecord.scan2, scanrecord.scan1,
                 scanrecord.scan0 ]
    Nscan = 0
    for scannum in range(len(scanlist)):
        thisscan = scanlist.pop()
        Nscan = Nscan + 1
        if (thisscan.Eena.get() == 1):
            scanrecord.current_scan.put('Scan {}'.format(Nscan))
            erange = [thisscan.e1s.get(), thisscan.e2s.get(), thisscan.e3s.get(), thisscan.efs.get()]
            estep = [thisscan.e1i.get(), thisscan.e2i.get(), thisscan.e3i.get()]
            waittime = thisscan.Ewait.get()

            xstart = thisscan.p1s.get()
            ystart = thisscan.p2s.get()
            # Move stages to the next point
            yield from mv(hf_stage.x, xstart,
                          hf_stage.y, ystart)
            acqtime = thisscan.acq.get()

            hfxanes_gen = yield from xanes_plan(erange=erange, estep=estep, acqtime=thisscan.acq.get(),
                                                samplename=thisscan.sampname.get(), filename=thisscan.filename.get(),
                                                roinum=int(thisscan.roi.get()), detune=thisscan.detune.get(), shutter=shutter)
            if (len(scanlist) is not 0):
                yield from bps.sleep(waittime)
    scanrecord.current_scan.put('')


def fast_shutter_per_step(detectors, motor, step):
    def move():
        grp = _short_uid('set')
        yield Msg('checkpoint')
        yield Msg('set', motor, step, group=grp)
        yield Msg('wait', None, group=grp)

    yield from move()
    # Open and close the fast shutter (Mo Foil) between XANES points
    # Open the shutter
    yield from mv(Mo_shutter, 0)
    yield from bps.sleep(1.0)
    # Step? trigger xspress3
    yield from trigger_and_read(list(detectors) + [motor])
    # Close the shutter
    yield from mv(Mo_shutter, 1)


class FlyerIDMono:
    def __init__(self, flying_dev, zebra, xs_detectors, scaler, pulse_cpt=None, pulse_width=0.01, paused_timeout=120):
        """Instantiate a flyer based on ID-Mono coordinated motion.

        Parameters
        ----------
        flying_dev : IDFlyDevice
            ID-Mono fly device that has controls of the DCM and ID energies

        zebra : SRXZebra
            zebra ophyd object

        xs_detectors : list
            a list of ophyd objects for corresponding xspress3 detectors

        scaler : SRXScaler
            an ophyd object for the scaler detector

        pulse_cpt : str
            an ophyd component name corresponding to the pulse signal

        pulse_width : float
            the pulse width in seconds, used for zebra

        paused_timeout : float
            the timeout to wait between the steps until the scan is interrupted if the "unpause" button is not pressed.
        """
        self.name = 'FlyerIDMono'

        self.flying_dev = flying_dev
        self.zebra = zebra
        self.xs_detectors = xs_detectors
        self.scaler = scaler

        # The pulse width has to be set both in Zebra and the Scan Engine.
        if pulse_cpt is None:
            raise RuntimeError(f'pulse_cpt cannot be None. Please provide a valid component name.')
        self.pulse_cpt = pulse_cpt
        self.pulse_width = pulse_width

        self.num_scans = None
        self.num_triggers = None

        self.paused_timeout = paused_timeout
        self._continue_after_pausing = True

        # TODO: These parameters are for the bpmAD camera, move them to the relevant class in 21-cameras.
        # self.plugin_type = 'tiff'

        # Flyer infrastructure parameters.
        self._traj_info = {}
        self._array_size = {}
        self._datum_ids = []

    def stage(self):
        # total_points = self.num_scans * self.num_triggers
        total_points = self.num_triggers

        for xs_det in self.xs_detectors:
            xs_det.hdf5.file_write_mode.put('Stream')
            xs_det.external_trig.put(True)
            xs_det.total_points.put(total_points)
            xs_det.spectra_per_point.put(1)
            xs_det.stage()
            xs_det.settings.acquire.put(1)

        # Scaler config
        self.scaler.count_mode.put(0)  # put SIS3820 into single count (not autocount) mode
        self.scaler.stop_all.put(1)  # stop scaler
        self.scaler.nuse_all.put(2*total_points)
        self.scaler.erase_start.put(1)

        # TODO: These parameters are for the bpmAD camera, move them to the relevant class in 21-cameras.
        # # This sets a filepath (template for TIFFs) and generates a Resource
        # # document in the detector.tiff Device's asset cache.
        # self.detector.is_flying = True
        # self.detector.stage_sigs['cam.image_mode'] = 'Multiple'
        # self.detector.stage_sigs['cam.trigger_mode'] = 'Sync In 2'
        # self.detector.stage_sigs['cam.array_counter'] = 0
        # self.detector.stage()
        # self.detector.cam.acquire.put(1)

    def unstage(self):
        for xs_det in self.xs_detectors:
            xs_det.settings.acquire.put(0)
            xs_det.hdf5.capture.put(0)  # this is to save the file is the number of collected frames is less than expected
            xs_det.settings.trigger_mode.put('Internal')
            xs_det.unstage()

        print(f"{print_now()}: before unstaging scaler")
        self.scaler.stop_all.put(1)
        print(f"{print_now()}: after unstaging scaler")

        # TODO: These parameters are for the bpmAD camera, move them to the relevant class in 21-cameras.
        # self.detector.unstage()
        # self.detector.is_flying = False
        # self.detector.cam.acquire.put(0)

    def kickoff(self, *args, **kwargs):

        # Reset zebra to clear the data entries.
        self.zebra.pc.block_state_reset.put(1)

        # Arm zebra.
        self.zebra.pc.arm.put(1)

        # PULSE tab of the Zebra CSS:
        getattr(self.zebra, self.pulse_cpt).input_addr.put(1)            # 'Input' in CSS, 1=IN1_TTL
        getattr(self.zebra, self.pulse_cpt).input_edge.put(0)            # 'Trigger on' in CSS, 0=Rising, 1=Falling
        getattr(self.zebra, self.pulse_cpt).delay.put(0.0)               # 'Delay before' in CSS
        getattr(self.zebra, self.pulse_cpt).width.put(self.pulse_width)  # 'First Pulse' in CSS
        getattr(self.zebra, self.pulse_cpt).time_units.put('s')          # 'Time Units' in CSS

        # SYS tab of the Zebra CSS
        # for out in [1, 2, 3, 4]:
        for out in [1, 2, 4]:
            getattr(self.zebra, f'output{out}').ttl.addr.put(52)          # 'OUTx TTL' in CSS

        # TESTING
        self.zebra.output3.ttl.addr.put(36)

        self.zebra.pulse3.input_addr.put(52)
        self.zebra.pulse3.input_edge.put(0)
        self.zebra.pulse3.time_units.put('ms')
        self.zebra.pulse3.width.put(0.500)
        self.zebra.pulse3.delay.put(0.0)

        self.zebra.pulse4.input_addr.put(52)
        self.zebra.pulse4.input_edge.put(1)
        self.zebra.pulse4.time_units.put('ms')
        self.zebra.pulse4.width.put(0.500)
        self.zebra.pulse4.delay.put(0.0)

        width_s = self.pulse_width
        speed = self.flying_dev.parameters.speed.get()

        self.num_scans = num_scans = self.flying_dev.parameters.num_scans.get()
        self.num_triggers = num_triggers = int(self.flying_dev.parameters.num_triggers.get())

        self.flying_dev.parameters.paused_timeout.put(self.paused_timeout)

        self._traj_info.update({
            'num_triggers': num_triggers,
            'energy_start': self.flying_dev.parameters.first_trigger.get(),
            'energy_stop': self.flying_dev.parameters.last_trigger.get(),
            })

        # TODO: These parameters are for the bpmAD camera, move them to the relevant class in 21-cameras.
        # self._array_size.update({'height': getattr(self.detector, self.plugin_type).array_size.height.get(),
        #                          'width': getattr(self.detector, self.plugin_type).array_size.width.get()})
        # self.detector.cam.num_images.put(num_scans * num_triggers)

        self.stage()

        # Convert to eV/s.
        # width_ev = width_s * speed
        # self.flying_dev.parameters.trigger_width.put(width_ev)

        enabled = int(round(self.flying_dev.control.control.get()))
        if enabled != 5:
            print(f'Enabling fly scan')
            self.flying_dev.control.control.put(1)

        # Reset the trigger count and current scan:
        self.flying_dev.parameters.trigger_count_reset.put(1)
        self.flying_dev.parameters.current_scan_reset.put(1)

        ttime.sleep(0.5)

        # Main RUN command:
        self.flying_dev.control.run.put(1)

        self.status = self.flying_dev.control.scan_in_progress

        def callback(value, old_value, **kwargs):
            print(f'{print_now()} in kickoff: {old_value} ---> {value}')
            if int(round(old_value)) == 0 and int(round(value)) == 1:
                return True
            return False

        status = SubscriptionStatus(self.status, callback)
        return status

    def complete(self, *args, **kwargs):
        if self.xs_detectors[0]._staged.value == 'no':

            # Note: this is a way to stop the scan on the flyL
            if self.flying_dev.parameters.num_scans.get() == 0:
                self._continue_after_pausing = False
                self.flying_dev.control.abort.put(1)

            if self._continue_after_pausing:
                self.stage()
                self.flying_dev.parameters.scan_paused.put(0)

        def _complete_detectors():
            print(f"{print_now()} run 'complete' on detectors.")
            # ttime.sleep(0.5)
            for xs_det in self.xs_detectors:
                print(f"{print_now()} before erase in '_complete_detectors'.")
                xs_det.erase.put(1)
                print(f"{print_now()} after erase in '_complete_detectors'.")
                xs_det.complete()
            print(f"{print_now()} done with 'complete' on detectors.")

        def callback_paused(value, old_value, **kwargs):
            print(f"{print_now()} 'callback_paused' in complete:  scan_paused: {old_value} ---> {value}")
             # 1=Paused, 0=Not Paused
            if int(round(old_value)) == 0 and int(round(value)) == 1:
                _complete_detectors()
                return True
            return False

        def callback_all_scans_done(value, old_value, **kwargs):
            print(f"{print_now()} 'callback_all_scans_done' in complete:  current_scan: {old_value} ---> {value}")
            if value == self.flying_dev.parameters.num_scans.get():  # last scan in the series, no pausing happens
                _complete_detectors()
                self.zebra.pc.disarm.put(1)
                return True
            return False

        current_scan = self.flying_dev.parameters.current_scan.get()
        num_scans = self.flying_dev.parameters.num_scans.get()

        if  current_scan + 1 < num_scans:  # last scan
            status_paused = SubscriptionStatus(self.flying_dev.parameters.scan_paused, callback_paused, run=False)
            return status_paused
        elif current_scan + 1 == num_scans:
            status_all_scans_done = SubscriptionStatus(self.flying_dev.parameters.current_scan, callback_all_scans_done, run=False)
            return status_all_scans_done
        else:
            return NullStatus()

    # TODO: Fix the configuration (also for v2).
    # def describe_configuration(self, *args, **kwargs):
    #     ret = {}
    #     for xs_det in self.xs_detectors:
    #         ret[f'{xs_det}.name'] = xs_det.describe_configuration()
    #     return ret

    def describe_collect(self, *args, **kwargs):
        return_dict = {
            'primary':
                {'energy': {'source': self.flying_dev.name,
                            'dtype': 'number',
                            # We need just 1 scalar value for the energy.
                            # 'shape': [self._traj_info['num_triggers']]},
                            # TODO: double-check the shape is right for databroker v2.
                            'shape': []},
                 'i0_time': {'source': 'scaler', 'dtype': 'array', 'shape': []},
                 'i0': {'source': 'scaler', 'dtype': 'array', 'shape': []},
                 'im': {'source': 'scaler', 'dtype': 'array', 'shape': []},
                 'it': {'source': 'scaler', 'dtype': 'array', 'shape': []},
                 # f'{self.detector.name}_image': {'source': '...',
                 #           'dtype': 'array',
                 #           'shape': [self._array_size['height'],
                 #                     self._array_size['width']],
                 #           'external': 'FILESTORE:'}
                }
        }
        for xs_det in self.xs_detectors:
            for channel in xs_det.channels.keys():
                return_dict['primary'][f'{xs_det.name}_ch{channel}'] = {'source': 'xspress3',
                                                                        'dtype': 'array',
                                                                        # The shape will correspond to a 1-D array of 4096 bins from xspress3.
                                                                        'shape': [
                                                                                  # We don't need the total number of frames here.
                                                                                  # xs_det.settings.num_images.get(),
                                                                                  #
                                                                                  # The height corresponds to a number of channels, but we only need one here.
                                                                                  # xs_det.hdf5.array_size.height.get(),
                                                                                  #
                                                                                  xs_det.hdf5.array_size.width.get()],
                                                                        'external': 'FILESTORE:'}
        # import pprint
        # pprint.pprint(return_dict)
        return return_dict

    def collect(self, *args, **kwargs):

        # TODO: test that feature.
        if not self._continue_after_pausing:
            return {}

        energy_start = self._traj_info['energy_start']
        energy_stop = self._traj_info['energy_stop']
        num_triggers = self._traj_info['num_triggers']

        # if len(self._datum_ids) != num_triggers:
        #     raise RuntimeError(f"The number of collected datum ids ({self._datum_ids}) "
        #                        f"does not match the number of triggers ({num_triggers})")

        ttime.sleep(self.pulse_width + 0.1)

        orig_read_attrs = self.scaler.read_attrs
        self.scaler.read_attrs = ['mca1', 'mca2', 'mca3', 'mca4']

        total_points = self.num_scans * self.num_triggers

        print(f"{print_now()}: before while loop in collect")
        flag_collecting_data = 0
        while (flag_collecting_data < 5):
            scaler_mca_data = self.scaler.read()
            i0_time = scaler_mca_data[f"{self.scaler.name}_mca1"]['value']
            i0 = scaler_mca_data[f"{self.scaler.name}_mca2"]['value']
            im = scaler_mca_data[f"{self.scaler.name}_mca3"]['value']
            it = scaler_mca_data[f"{self.scaler.name}_mca4"]['value']

            print(f'{i0_time.shape[0]}\t?=\t{2*self.num_triggers}')
            if i0_time.shape[0] == 2*self.num_triggers:
                break
            flag_collecting_data += 1
            ttime.sleep(0.2)
            print(f'({flag_collecting_data+1}/5) Waiting to collect all scaler data...')
        print(f"{print_now()}: after while loop in collect")

        self.scaler.read_attrs = orig_read_attrs

        print(f"Length of 'i0_time': {len(i0_time)}")
        print(f"Length of 'i0'     : {len(i0)}")
        print(f"Length of 'im'     : {len(im)}")
        print(f"Length of 'it'     : {len(it)}")

        i0_time = i0_time[1::2]
        i0 = i0[1::2]
        im = im[1::2]
        it = it[1::2]

        print(f"Truncated length of 'i0_time': {len(i0_time)}")
        print(f"Truncated length of 'i0'     : {len(i0)}")
        print(f"Truncated length of 'im'     : {len(im)}")
        print(f"Truncated length of 'it'     : {len(it)}")

        if len(i0_time) != len(i0) != len(im) != len(it):
            raise RuntimeError(f"Lengths of the collected arrays are not equal")

        print(f"{print_now()}: before unstage of xs in collect")

        # Unstage xspress3 detector(s).
        self.unstage()

        print(f"{print_now()}: after unstage of xs in collect")

        # Deal with the direction of energies for bi-directional scan.
        # BlueSky@SRX [27]: id_fly_device.control.scan_type.get(as_string=True)
        # Out[27]: 'Bidirectional'

        # BlueSky@SRX [28]: id_fly_device.control.scan_type.enum_strs
        # Out[28]: ('Unidirectional', 'Bidirectional')

        even_direction = np.linspace(energy_start, energy_stop, num_triggers)
        odd_direction =  even_direction[::-1]

        scan_type = self.flying_dev.control.scan_type.get(as_string=True)
        current_scan = self.flying_dev.parameters.current_scan.get()
        print(f"{print_now()} the scan is {scan_type}; current scan: {current_scan}")

        direction = even_direction
        if scan_type == "Bidirectional":
            if (current_scan + 1) % 2 == 1:  # at this point the current scan number is already incremented
                direction = odd_direction
                print(f"{print_now()} reversing the energy axis: {direction[0]} --> {direction[-1]}")

        for ii, energy in enumerate(direction):
            for xs_det in self.xs_detectors:
                now = ttime.time()

                data = {
                    'energy': energy,
                    'i0_time': i0_time[ii],
                    'i0': i0[ii],
                    'im': im[ii],
                    'it': it[ii],
                }
                timestamps = {
                    'energy': now,
                    'i0_time': now,
                    'i0': now,
                    'im': now,
                    'it': now,
                }
                filled = {}
                for jj, channel in enumerate(xs_det.channels.keys()):
                    key = f'{xs_det.name}_ch{channel}'
                    idx = jj + ii * len(xs_det.channels.keys())
                    try:
                        data[key] = xs_det._datum_ids[idx]
                    except IndexError:
                        print('Waiting 10 seconds for data...')
                        ttime.sleep(10)
                        data[key] = xs_det._datum_ids[idx]
                    timestamps[key] = now
                    filled[key] = False

            yield {
                'data': data,
                'timestamps': timestamps,
                'time': now,
                'seq_num': i,
                'filled': filled,
            }

        print(f"{print_now()}: after docs emitted in collect")


    def collect_asset_docs(self):
        print(f"{print_now()}: before collecting asset docs from xs in collect_asset_docs")
        for xs_det in self.xs_detectors:
            yield from xs_det.collect_asset_docs()
        print(f"{print_now()}: after collecting asset docs from xs in collect_asset_docs")


flyer_id_mono = FlyerIDMono(flying_dev=id_fly_device,
                            zebra=nanoZebra,
                            xs_detectors=[xs_id_mono_fly],
                            scaler=sclr1,
                            pulse_cpt='pulse1',
                            pulse_width=0.05)


# Helper functions for quick vis:
def plot_flyer_id_mono_data(uid_or_scanid, e_min=None, e_max=None, fname=None, root='/home/xf05id1/current_user_data/', num_channels=4):
    hdr = db[uid_or_scanid]
    tbl = hdr.table()
    # N = 
    if (e_min is None):
        e_min = xs.channel1.rois.roi01.bin_low.get()
    if (e_max is None):
        e_max = xs.channel1.rois.roi01.bin_high.get()

    if (fname is None):
        fname = f"scan{hdr.start['scan_id']}.txt"
    fname = root + fname

    d = []
    for i in range(num_channels):
        d.append(np.array(list(hdr.data(f'xs_id_mono_fly_ch{i + 1}')))[:, e_min:e_max].sum(axis=1))
    d = np.array(d)

    i0 = np.array(tbl['i0'])
    energy = np.array(tbl['energy'])

    spectrum_unnormalized = d.sum(axis=0)
    spectrum = spectrum_unnormalized / i0

    res = np.vstack((energy, i0, spectrum_unnormalized, spectrum))
    res = res.T

    fig, ax = plt.subplots()
    # for i in range(N):
        
    ax.plot(energy, spectrum)
    ax.set(xlabel='Energy [eV]', ylabel='Normalized Spectrum [Arb]')
    np.savetxt(fname, res)
    return res.T

def flying_xas(num_passes=1, shutter=True, md=None):
    v = flyer_id_mono.flying_dev.parameters.speed.get()
    w = flyer_id_mono.flying_dev.parameters.trigger_width.get()
    dt = w / v
    flyer_id_mono.pulse_width = dt
    yield from check_shutters(shutter, 'Open')
    yield from bp.fly([flyer_id_mono])
    # yield from fly_multiple_passes([flyer_id_mono], num_passes=num_passes,
    #                                md=md, shutter=shutter)
    yield from check_shutters(shutter, 'Close')


def fly_multiple_passes(e_start, e_stop, e_width, dwell, num_pts, *,
                        num_scans=1, shutter=True,
                        flyers=[flyer_id_mono], md=None):
    """This is a modified version of bp.fly to support multiple passes of the flyer."""

    flyer_id_mono.flying_dev.parameters.first_trigger.put(e_start)
    flyer_id_mono.flying_dev.parameters.last_trigger.put(e_stop)
    flyer_id_mono.flying_dev.parameters.trigger_width.put(e_width)
    flyer_id_mono.flying_dev.parameters.num_triggers.put(num_pts)
    flyer_id_mono._traj_info['num_triggers'] = num_pts
    flyer_id_mono._traj_info['energy_start'] = e_start
    flyer_id_mono._traj_info['energy_stop'] = e_stop
    flyer_id_mono._traj_info['energy_width'] = e_width

    v = e_width / dwell
    flyer_id_mono.flying_dev.parameters.speed.put(v)
    e_step = (e_stop - e_start) / (num_pts- 1)
    dt = e_width / v

    if (abs(e_step) < e_width):
        raise ValueError('Cannot have energy collection widths larger than energy step!')

    yield from check_shutters(shutter, 'Open')

    if md is None:
        md = {}
    md = get_stock_md(md)
    md['scan']['num_scans'] = num_scans
    md['scan']['num_points'] = num_pts
    md['scan']['type'] = 'XAS_FLY'

    uid = yield from bps.open_run(md)
    for flyer in flyers:
        flyer.pulse_width = dwell
        yield from bps.mv(flyer.flying_dev.parameters.num_scans, num_scans)
        yield from bps.kickoff(flyer, wait=True)
    for n in range(num_scans):
        print(f"\n\n*** {print_now()} Iteration #{n+1} ***\n")
        for flyer in flyers:
            yield from bps.complete(flyer, wait=True)
        for flyer in flyers:
            yield from bps.collect(flyer)
    yield from bps.close_run()
    yield from check_shutters(shutter, 'Close')
    return uid


"""
TODO: All scan directions and modes (uni/bi-directional)
TODO: setup stage_sigs for scaler
TODO: Monitor and LivePlot of data
TODO: Unstage the detectors (xs, scaler) on RE.abort()
"""
