import glob
import os

import corgidrp.data as data
from corgidrp.l1_to_l2a import prescan_biassub
import corgidrp.mocks as mocks

import numpy as np
import yaml
from astropy.io import fits
from pathlib import Path

from pytest import approx

# Expected output image shapes
shapes = {
    'SCI' : {
        True : (1200,2200),
        False : (1024,1024)
    },
    'ENG' : {
        True: (2200,2200),
        False : (1024,1024)
    }
}

# Copy-pasted II&T code

# Metadata code from https://github.com/roman-corgi/cgi_iit_drp/blob/main/proc_cgi_frame_NTR/proc_cgi_frame/read_metadata.py

class ReadMetadataException(Exception):
    """Exception class for read_metadata module."""

# Set up to allow the metadata.yaml in the repo be the default
here = Path(os.path.dirname(os.path.abspath(__file__)))
meta_path = Path(here,'test_data','metadata.yaml')

class Metadata(object):
    """ II&T pipeline class to store metadata.
    
    B Nemati and S Miller - UAH - 03-Aug-2018

    Args:
        meta_path (str): Full path of metadta yaml.

    Attributes:
        data (dict):
            Data from metadata file.
        geom (SimpleNamespace):
            Geometry specific data.
    """

    def __init__(self, meta_path=meta_path):
        self.meta_path = meta_path

        self.data = self.get_data()
        self.frame_rows = self.data['frame_rows']
        self.frame_cols = self.data['frame_cols']
        self.geom = self.data['geom']

    def get_data(self):
        """Read yaml data into dictionary.
        
        Returns:
            data (dict): Metadata dictionary.
        """
        with open(self.meta_path, 'r') as stream:
            data = yaml.safe_load(stream)
        return data

    def slice_section(self, frame, key):
        """Slice 2d section out of frame.

        Args:
            frame (array_like): 
                Full frame consistent with size given in frame_rows, frame_cols.
            key (str): 
                Keyword referencing section to be sliced; must exist in geom.
        
        Returns:
            section (array_like): Section of frame
        """
        rows, cols, r0c0 = self._unpack_geom(key)

        section = frame[r0c0[0]:r0c0[0]+rows, r0c0[1]:r0c0[1]+cols]
        if section.size == 0:
            raise ReadMetadataException('Corners invalid')
        return section

    def _unpack_geom(self, key):
        """Safely check format of geom sub-dictionary and return values.
        
        Args:
            key (str): Keyword referencing section to be sliced; must exist in geom.

        Returns:
            rows (int): Number of rows in section.
            cols (int): Number of columns in section.
            r0c0 (tuple): Initial row and column of section.
        """
        coords = self.geom[key]
        rows = coords['rows']
        cols = coords['cols']
        r0c0 = coords['r0c0']

        return rows, cols, r0c0

    #added in from MetadataWrapper
    def _imaging_area_geom(self):
        """Return geometry of imaging area in reference to full frame.
        
        Returns:
            rows_im (int): Number of rows corresponding to image frame.
            cols_im (int): Number of columns in section.
            r0c0_im (tuple): Initial row and column of section.
        """

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

        Args:
            frame (array_like): 
                Full frame consistent with size given in frame_rows, frame_cols.
            
        Returns:
            slice (array_like): 
                Science image area of full frame.
        """
        rows, cols, r0c0 = self._imaging_area_geom()

        slice = frame[r0c0[0]:r0c0[0]+rows, r0c0[1]:r0c0[1]+cols]

        return slice
    
# EMCCDFrame code from https://github.com/roman-corgi/cgi_iit_drp/blob/main/proc_cgi_frame_NTR/proc_cgi_frame/gsw_emccd_frame.py#L9

# EMCCDFrame code from https://github.com/roman-corgi/cgi_iit_drp/blob/main/proc_cgi_frame_NTR/proc_cgi_frame/gsw_emccd_frame.py#L9

class EMCCDFrameException(Exception):
    """Exception class for emccd_frame module."""

class EMCCDFrame:
    """Get data from EMCCD frame and subtract the bias and bias offset.

    S Miller - UAH - 16-April-2019

    Args:
        frame_dn (array_like): 
            Raw EMCCD full frame (DN).
        meta (instance): 
            Instance of Metadata class containing detector metadata.
        fwc_em (float): 
            Detector EM gain register full well capacity (DN).
        fwc_pp (float): 
            Detector image area per-pixel full well capacity (DN).
        em_gain (float): 
            Gain from EM gain register, >= 1 (unitless).
        bias_offset (float): 
            Median number of counts in the bias region due to fixed non-bias noise
            not in common with the image region.  Basically we compute the bias
            for the image region based on the prescan from each frame, and the
            bias_offset is how many additional counts the prescan had from extra
            noise not captured in the master dark fit.  This value is subtracted
            from each measured bias.  Units of DN.

    Attributes:
        image (array_like): 
            Image section of frame (DN).
        prescan (array_like): 
            Prescan section of frame (DN).
        al_prescan (array_like): 
            Prescan with row numbers relative to the first image row (DN).
        frame_bias (array_like): 
            Column vector with each entry the median of the prescan row minus the
            bias offset (DN).
        bias (array_like): 
            Column vector with each entry the median of the prescan row relative
            to the first image row minus the bias offset (DN).
        frame_bias0 (array_like): 
            Total frame minus the bias (row by row) minus the bias offset (DN).
        image_bias0 (array_like): 
            Image area minus the bias (row by row) minus the bias offset (DN).
    """

    def __init__(self, frame_dn, meta, fwc_em, fwc_pp, em_gain, bias_offset):
        self.frame_dn = frame_dn
        self.meta = meta
        self.fwc_em = fwc_em
        self.fwc_pp = fwc_pp
        self.em_gain = em_gain
        self.bias_offset = bias_offset

        # Divide frame into sections
        try:
            self.image = self.meta.slice_section(self.frame_dn, 'image')
            self.prescan = self.meta.slice_section(self.frame_dn, 'prescan')
        except Exception:
            raise EMCCDFrameException('Frame size inconsistent with metadata')

        # Get the part of the prescan that lines up with the image, and do a
        # row-by-row bias subtraction on it
        i_r0 = self.meta.geom['image']['r0c0'][0]
        p_r0 = self.meta.geom['prescan']['r0c0'][0]
        i_nrow = self.meta.geom['image']['rows']
        # select the good cols for getting row-by-row bias
        st = self.meta.geom['prescan']['col_start']
        end = self.meta.geom['prescan']['col_end']
        # over all prescan rows
        medbyrow_tot = np.median(self.prescan[:,st:end], axis=1)[:, np.newaxis]
        # prescan relative to image rows
        self.al_prescan = self.prescan[(i_r0-p_r0):(i_r0-p_r0+i_nrow), :]
        medbyrow = np.median(self.al_prescan[:,st:end], axis=1)[:, np.newaxis]

        # Get data from prescan (image area)
        self.bias = medbyrow - self.bias_offset
        self.image_bias0 = self.image - self.bias

        # over total frame
        self.frame_bias = medbyrow_tot - self.bias_offset
        self.frame_bias0 = self.frame_dn[p_r0:, :] -  self.frame_bias


# Run tests

def test_prescan_sub():
    """
    Generate mock raw data ('SCI' & 'ENG') and pass into prescan processing function. 
    Check output dataset shapes, maintain pointers in the Dataset and Image class,
    and check that output is consistent with results II&T code.

    TODO: 
    * test function of different bias offsets
    """
    ###### create simulated data
    # check that simulated data folder exists, and create if not
    datadir = os.path.join(os.path.dirname(__file__), "simdata")
    if not os.path.exists(datadir):
        os.mkdir(datadir)

    for obstype in ['SCI', 'ENG']:
        # create simulated data
        dataset = mocks.create_prescan_files(filedir=datadir, obstype=obstype)

        filenames = glob.glob(os.path.join(datadir, f"sim_prescan_{obstype}*.fits"))

        dataset = data.Dataset(filenames)

        iit_images = []
        iit_frames = []

        # II&T version
        for fname in filenames:
            
            l1_data = fits.getdata(fname)

            # Read in data
            meta_path = Path(here,'test_data','metadata.yaml') if obstype == 'SCI' else Path(here,'test_data','metadata_eng.yaml')
            meta = Metadata(meta_path = meta_path)
            frameobj = EMCCDFrame(l1_data,
                                    meta,
                                    1., # fwc_em_dn
                                    1., # fwc_pp_dn
                                    1., # em_gain
                                    0.) # bias_offset

            # Subtract bias and bias offset and get cosmic mask
            iit_images.append(frameobj.image_bias0) # Science area
            iit_frames.append(frameobj.frame_bias0) # Full frame
            
        if len(dataset) != 2:
            raise Exception(f"Mock dataset is an unexpected length ({len(dataset)}).")
        
        for return_full_frame in [True, False]:
            output_dataset = prescan_biassub(dataset, return_full_frame=return_full_frame)

            output_shape = output_dataset[0].data.shape
            if output_shape != shapes[obstype][return_full_frame]:
                raise Exception(f"Shape of output frame for {obstype}, return_full_frame={return_full_frame} is {output_shape}, \nwhen {shapes[obstype][return_full_frame]} was expected.")
    
            # check that data, err, and dq arrays are consistently modified
            dataset.all_data[0, 0, 0] = 0.
            if dataset[0].data[0, 0] != 0. :
                raise Exception("Modifying dataset.all_data did not modify individual frame data.")

            dataset[0].data[0,0] = 1.
            if dataset.all_data[0,0,0] != 1. :
                raise Exception("Modifying individual frame data did not modify dataset.all_data.")

            dataset.all_err[0, 0, 0] = 0.
            if dataset[0].err[0, 0] != 0. :
                raise Exception("Modifying dataset.all_err did not modify individual frame err.")

            dataset[0].err[0,0] = 1.
            if dataset.all_err[0,0,0] != 1. :
                raise Exception("Modifying individual frame err did not modify dataset.all_err.")

            dataset.all_dq[0, 0, 0] = 0.
            if dataset[0].dq[0, 0] != 0. :
                raise Exception("Modifying dataset.all_dq did not modify individual frame dq.")

            dataset[0].dq[0,0] = 1.
            if dataset.all_dq[0,0,0] != 1. :
                raise Exception("Modifying individual frame dq did not modify dataset.all_dq.")
            
            corgidrp_result = output_dataset[0].data
            iit_result = iit_frames[0] if return_full_frame else iit_images[0]

            if not corgidrp_result == approx(iit_result):
                raise Exception(f"corgidrp result does not match II&T result for generated mock data, obstype={obstype}, return_full_frame={return_full_frame}.")

            # Plot for debugging
            # fig,axes = plt.subplots(1,3,figsize=(10,4))

            # im0 = axes[0].imshow(corgidrp_result,cmap='seismic')
            # plt.colorbar(im0)
            # axes[0].set_title('corgidrp result')

            # im1 = axes[1].imshow(iit_result,cmap='seismic')
            # plt.colorbar(im1)
            # axes[1].set_title('II&T result')

            # im2 = axes[2].imshow(corgidrp_result-iit_result,cmap='seismic')
            # plt.colorbar(im2)
            # axes[2].set_title('Difference')

            # plt.tight_layout()
            # plt.show()


if __name__ == "__main__":
    test_prescan_sub()
    