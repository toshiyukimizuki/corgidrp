# Place to put detector-related utility functions

import numpy as np
import corgidrp.data as data
from scipy import interpolate
from astropy.time import Time
import os
from pathlib import Path
import yaml

class ReadMetadataException(Exception):
    """Exception class for read_metadata module."""

# Set up to allow the metadata.yaml in the repo be the default
here = Path(os.path.dirname(os.path.abspath(__file__)))
meta_path = Path(here, 'util', 'metadata.yaml')

class Metadata(object):
    """Create masks for different regions of the Roman CGI EXCAM detector.

    Parameters
    ----------
    meta_path : str
        Full path of metadta yaml.

    Attributes
    ----------
    data : dict
        Data from metadata file.
    geom : SimpleNamespace
        Geometry specific data.

    B Nemati and S Miller - UAH - 03-Aug-2018

    """

    def __init__(self, meta_path=meta_path, obstype='SCI'):
        self.meta_path = meta_path

        self.data = self.get_data()
        self.obstype = obstype
        self.frame_rows = self.data[obstype]['frame_rows']
        self.frame_cols = self.data[obstype]['frame_cols']
        self.geom = self.data[obstype]['geom']

    def get_data(self):
        """Read yaml data into dictionary."""
        with open(self.meta_path, 'r') as stream:
            data = yaml.safe_load(stream)
        return data

    def slice_section(self, frame, key):
        """Slice 2d section out of frame.

        Parameters
        ----------
        frame : array_like
            Full frame consistent with size given in frame_rows, frame_cols.
        key : str
            Keyword referencing section to be sliced; must exist in geom.

        """
        rows, cols, r0c0 = self._unpack_geom(key)

        section = frame[r0c0[0]:r0c0[0]+rows, r0c0[1]:r0c0[1]+cols]
        if section.size == 0:
            raise ReadMetadataException('Corners invalid')
        return section

    def _unpack_geom(self, key):
        """Safely check format of geom sub-dictionary and return values."""
        coords = self.geom[key]
        rows = coords['rows']
        cols = coords['cols']
        r0c0 = coords['r0c0']

        return rows, cols, r0c0

    #added in from MetadataWrapper
    def _imaging_area_geom(self):
        """Return geometry of imaging area in reference to full frame."""
        _, cols_pre, _ = self._unpack_geom('prescan')
        _, cols_serial_ovr, _ = self._unpack_geom('serial_overscan')
        rows_parallel_ovr, _, _ = self._unpack_geom('parallel_overscan')
        #_, _, r0c0_image = self._unpack_geom('image')
        fluxmap_rows, _, r0c0_image = self._unpack_geom('image')

        rows_im = self.frame_rows - rows_parallel_ovr
        cols_im = self.frame_cols - cols_pre - cols_serial_ovr
        r0c0_im = r0c0_image.copy()
        r0c0_im[0] = r0c0_im[0] - (rows_im - fluxmap_rows)

        return rows_im, cols_im, r0c0_im

    def imaging_slice(self, frame):
        """Select only the real counts from full frame and exclude virtual.

        Use this to transform mask and embed from acting on the full frame to
        acting on only the image frame.

        """
        rows, cols, r0c0 = self._imaging_area_geom()

        return frame[r0c0[0]:r0c0[0]+rows, r0c0[1]:r0c0[1]+cols]


def create_dark_calib(dark_dataset):
    """
    Turn this dataset of image frames that were taken to measure
    the dark current into a dark calibration frame and determines the corresponding error

    Args:
        dark_dataset (corgidrp.data.Dataset): a dataset of Image frames (L2a-level)

    Returns:
        data.Dark: a dark calibration frame
    """
    combined_frame = np.nanmean(dark_dataset.all_data, axis=0)

    new_dark = data.Dark(combined_frame, pri_hdr=dark_dataset[0].pri_hdr.copy(),
                         ext_hdr=dark_dataset[0].ext_hdr.copy(), input_dataset=dark_dataset)

    # determine the standard error of the mean: stddev/sqrt(n_frames)
    new_dark.err = np.nanstd(dark_dataset.all_data, axis=0)/np.sqrt(len(dark_dataset))
    new_dark.err = new_dark.err.reshape((1,)+new_dark.err.shape) #Get it into the right dimensions

    return new_dark

def get_relgains(frame, em_gain, non_lin_correction):
    """
    For a given bias subtracted frame of dn counts, return a same sized
    array of relative gain values.

    This algorithm contains two interpolations:

    - A 2d interpolation to find the relative gain curve for a given EM gain
    - A 1d interpolation to find a relative gain value for each given dn
      count value.

    Both of these interpolations are linear, and both use their edge values as
    constant extrapolations for out of bounds values.

    Parameters:
        frame (array_like): Array of dn count values.
        em_gain (float): Detector EM gain.
        non_lin_correction (corgi.drp.NonLinearityCorrection): A NonLinearityCorrection calibration file.

    Returns:
        array_like: Array of relative gain values.
    """

    # Column headers are gains, row headers are dn counts
    gain_ax = non_lin_correction.data[0, 1:]
    count_ax = non_lin_correction.data[1:, 0]
    # Array is relative gain values at a given dn count and gain
    relgains = non_lin_correction.data[1:, 1:]

    #MMB Note: This check is maybe better placed in the code that is saving the non-linearity correction file?
    # Check for increasing axes
    if np.any(np.diff(gain_ax) <= 0):
        raise ValueError('Gain axis (column headers) must be increasing')
    if np.any(np.diff(count_ax) <= 0):
        raise ValueError('Counts axis (row headers) must be increasing')
    # Check that curves (data in columns) contain or straddle 1.0
    if (np.min(relgains, axis=0) > 1).any() or \
       (np.max(relgains, axis=0) < 1).any():
        raise ValueError('Gain curves (array columns) must contain or '
                              'straddle a relative gain of 1.0')

    # Create interpolation for em gain (x), counts (y), and relative gain (z).
    # Note that this defaults to using the edge values as fill_value for
    # out of bounds values (same as specified below in interp1d)
    f = interpolate.RectBivariateSpline(gain_ax,
                                    count_ax,
                                    relgains.T,
                                    kx=1,
                                    ky=1,
    )
    # Get the relative gain curve for the given gain value
    relgain_curve = f(em_gain, count_ax)[0]

    # Create interpolation for dn counts (x) and relative gains (y). For
    # out of bounds values use edge values
    ff = interpolate.interp1d(count_ax, relgain_curve, kind='linear',
                              bounds_error=False,
                              fill_value=(relgain_curve[0], relgain_curve[-1]))
    # For each dn count, find the relative gain
    counts_flat = ff(frame.ravel())

    return counts_flat.reshape(frame.shape)

# detector_areas= {
#     'SCI' : {
#         'frame_rows' : 1200,
#         'frame_cols' : 2200,
#         'image' : {
#             'rows': 1024,
#             'cols': 1024,
#             'r0c0': [13, 1088]
#             },
#         'prescan' : {
#             'rows': 1200,
#             'cols': 1088,
#             'r0c0': [0, 0]
#             },
#         'prescan_reliable' : {
#             'rows': 1200,
#             'cols': 200,
#             'r0c0': [0, 800]
#             },
#         'parallel_overscan' : {
#             'rows': 163,
#             'cols': 1056,
#             'r0c0': [1037, 1088]
#             },
#         'serial_overscan' : {
#             'rows': 1200,
#             'cols': 56,
#             'r0c0': [0, 2144]
#             },
#         },
#     'ENG' :{
#         'frame_rows' : 2200,
#         'frame_cols' : 2200,
#         'image' : {
#             'rows': 1024,
#             'cols': 1024,
#             'r0c0': [13, 1088]
#             },
#         'prescan' : {
#             'rows': 2200,
#             'cols': 1088,
#             'r0c0': [0, 0]
#             },
#         'prescan_reliable' : {
#             'rows': 2200,
#             'cols': 200,
#             'r0c0': [0, 800]
#             },
#         'parallel_overscan' : {
#             'rows': 1163,
#             'cols': 1056,
#             'r0c0': [1037, 1088]
#             },
#         'serial_overscan' : {
#             'rows': 2200,
#             'cols': 56,
#             'r0c0': [0, 2144]
#             },
#         },
#     }

# NOTE The 2 functions below don't work with implementation of Metadata class.
# But they are used by anything either, so no need to fix these.  Masking
# handled via Metadata class, and plotting a visualization can be done via
# metadata_visualize.py.

# def plot_detector_areas(detector_areas, areas=('image', 'prescan',
#         'prescan_reliable', 'parallel_overscan', 'serial_overscan')):
#     """
#     Create an image of the detector areas for visualization and debugging

#     Args:
#         detector_areas (dict): a dictionary of image constants
#         areas (tuple): a tuple of areas to create masks for

#     Returns:
#         np.ndarray: an image of the detector areas
#     """
#     #detector_areas = make_detector_areas(detector_areas, areas=areas)
#     detector_area_image = np.zeros(
#         (detector_areas['frame_rows'], detector_areas['frame_cols']), dtype=int)
#     for i, area in enumerate(areas):
#         detector_area_image[detector_areas[area]] = i + 1
#     return detector_area_image

# def detector_area_mask(detector_areas, area='image'):
#     """
#     Create a mask for the detector area

#     Args:
#         detector_areas (dict): a dictionary of image constants
#         area (str): the area of the detector to create a mask for

#     Returns:
#         np.ndarray: a mask for the detector area
#     """
#     mask = np.zeros((detector_areas['frame_rows'], detector_areas['frame_cols']), dtype=bool)
#     mask[detector_areas[area]['r0c0'][0]:detector_areas[area]['r0c0'][0] + detector_areas[area]['rows'],
#             detector_areas[area]['r0c0'][1]:detector_areas[area]['r0c0'][1] + detector_areas[area]['cols']] = True
#     return mask

# NOTE:  Change the retrieval of rowreadtime_sec to a read-off of a .yaml or
# other config file which has the date in the filename?
def get_rowreadtime_sec(datetime=None, meta_path=None):
    """
    Get the value of readrowtime. The EMCCD is considered sensitive to the
    effects of radiation damage and, if this becomes a problem, one of the
    mitigation techniques would be to change the row read time to reduce the
    impact of charge traps.

    There's no formal plan/timeline for this adjustment, though it is possible
    to change in the future should it need to.

    Its default value is 223.5e-6 sec.

    Args:
        datetime (astropy Time object): Observation's starting date. Its default
            value is sometime between the first collection of ground data (Full
            Functional Tests) and the duration of the Roman Coronagraph mission.
        meta_path (string): Full path of .yaml file used for detector geometry.
            If None, defaults to corgidrp.util.metadata.yaml.

    Returns:
        rowreadtime (float): Current value of rowreadtime in sec.

    """
    # Some datetime between the first collection of ground data (Full
    # Functional Tests) and the duration of the Roman Coronagraph mission.
    if datetime is None:
        datetime = Time('2024-03-01 00:00:00', scale='utc')

    # IIT datetime
    datetime_iit = Time('2023-11-01 00:00:00', scale='utc')
    # Date well in the future to always fall in this case, unless rowreadtime
    # gets updated. One may add more datetime_# values to keep track of changes.
    datetime_1 = Time('2040-01-01 00:00:00', scale='utc')

    if datetime < datetime_iit:
        raise ValueError('The observation datetime cannot be earlier than first collected data on ground.')
    elif datetime < datetime_1:
        if meta_path is None:
            meta = Metadata()
        else:
            meta = Metadata(meta_path)
        rowreadtime_sec = meta.data['rowreadtime_sec']
    else:
        raise ValueError('The observation datetime cannot be later than the' + \
            ' end of the mission')

    return rowreadtime_sec
