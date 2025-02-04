import os
import sys
import json
import logging

from simple_mask_ui import Ui_SimpleMask as Ui
from simple_mask_kernel import SimpleMask
from PyQt5.QtWidgets import QFileDialog, QApplication, QMainWindow
import numpy as np
import pyqtgraph as pg


home_dir = os.path.join(os.path.expanduser('~'), '.simple-mask')
if not os.path.isdir(home_dir):
    os.mkdir(home_dir)
log_filename = os.path.join(home_dir, 'simple-mask.log')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(name)-24s: %(message)s',
                    handlers=[
                        logging.FileHandler(log_filename, mode='a'),
                        logging.StreamHandler()
                    ])

logger = logging.getLogger(__name__)


def exception_hook(exc_type, exc_value, exc_traceback):
    logger.error("Uncaught exception",
                 exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = exception_hook


def text_to_array(pts):
    for symbol in '[](),':
        pts = pts.replace(symbol, ' ')
    pts = pts.split(' ')
    pts = [int(x) for x in pts if x != '']
    pts = np.array(pts).astype(np.int64)

    return pts


class SimpleMaskGUI(QMainWindow, Ui):
    def __init__(self, path=None):

        super(SimpleMaskGUI, self).__init__()

        self.setupUi(self)
        self.btn_load.clicked.connect(self.load)
        self.btn_plot.clicked.connect(self.plot)
        self.btn_compute_qpartition.clicked.connect(self.compute_partition)
        self.btn_select_raw.clicked.connect(self.select_raw)
        # self.btn_select_txt.clicked.connect(self.select_txt)
        self.btn_update_parameters.clicked.connect(self.update_parameters)
        self.btn_swapxy.clicked.connect(
            lambda: self.update_parameters(swapxy=True))

        # need a function for save button -- simple_mask_ui
        self.pushButton.clicked.connect(self.save_mask)

        self.plot_index.currentIndexChanged.connect(self.mp1.setCurrentIndex)

        # simple mask kernep
        self.sm = SimpleMask(self.mp1, self.infobar)
        self.mp1.sigTimeChanged.connect(self.update_index)
        self.state = 'lock'

        # mask_list
        self.btn_mask_list_load.clicked.connect(self.mask_list_load)
        self.btn_mask_list_clear.clicked.connect(self.mask_list_clear)
        self.btn_mask_list_add.clicked.connect(self.mask_list_add)

        self.btn_mask_list_evaluate.clicked.connect(
            lambda: self.mask_evaluate('mask_list'))
        self.btn_mask_list_apply.clicked.connect(
            lambda: self.mask_apply('mask_list'))

        # blemish
        self.btn_select_blemish.clicked.connect(self.select_blemish)
        self.btn_apply_blemish.clicked.connect(
            lambda: self.mask_evaluate('mask_blemish'))
        self.btn_mask_blemish_apply.clicked.connect(
            lambda: self.mask_apply('mask_blemish'))

        # mask_file
        self.btn_select_maskfile.clicked.connect(self.select_maskfile)
        self.btn_apply_maskfile.clicked.connect(
            lambda: self.mask_evaluate('mask_file'))
        self.btn_mask_file_apply.clicked.connect(
            lambda: self.mask_apply('mask_file'))

        # draw method / array
        self.btn_mask_draw_add.clicked.connect(self.add_drawing)
        self.btn_mask_draw_evaluate.clicked.connect(
            lambda: self.mask_evaluate('mask_draw'))
        self.btn_mask_draw_apply.clicked.connect(
            lambda: self.mask_apply('mask_draw'))

        # binary threshold
        self.btn_mask_threshold_evaluate.clicked.connect(
            lambda: self.mask_evaluate('mask_threshold'))
        self.btn_mask_threshold_apply.clicked.connect(
            lambda: self.mask_apply('mask_threshold'))

        # btn_mask_outlier_evaluate
        self.btn_mask_outlier_evaluate.clicked.connect(
            lambda: self.mask_evaluate('mask_outlier'))
        self.btn_mask_outlier_apply.clicked.connect(
            lambda: self.mask_apply('mask_outlier'))

        self.mask_outlier_hdl.setBackground((255, 255, 255))
        self.mp1.scene.sigMouseClicked.connect(self.mouse_clicked)

        self.work_dir = None
        if path is not None:
            path = os.path.abspath(path)
            if os.path.isfile(path):
                self.fname.setText(str(path))
                self.work_dir = os.path.dirname(path)
            elif os.path.isdir(path):
                self.work_dir = path

        self.MaskWidget.setCurrentIndex(0)
        self.setting_fname = os.path.join(home_dir, 'default_setting.json')
        self.lastconfig_fname = os.path.join(home_dir, 'last_config.json')
        self.load_default_settings()
        self.load_last_config()
        self.show()

    def load_default_settings(self):
        # copy the default values
        if not os.path.isfile(self.setting_fname):
            config = {
                "window_size_w": 1400,
                "window_size_h": 740
            }
            with open(self.setting_fname, 'w') as f:
                json.dump(config, f, indent=4)

        # the display size might too big for some laptops
        with open(self.setting_fname, 'r') as f:
            config = json.load(f)
            if "window_size_h" in config:
                new_size = (config["window_size_w"], config["window_size_h"])
                logger.info('set mainwindow to size %s', new_size)
                self.resize(*new_size)

        return

    def mouse_clicked(self, event):
        if not event.double():
            return

        # make sure the maskwidget is at manual mode;
        if self.MaskWidget.currentIndex() != 3:
            return

        if not self.mp1.scene.itemsBoundingRect().contains(event.pos()):
            return

        mouse_point = self.mp1.getView().mapSceneToView(event.pos())
        col = int(mouse_point.x())
        row = int(mouse_point.y())
        if not self.mask_list_include.isChecked():
            self.mask_list_add_pts([np.array([col, row])])
        else:
            kwargs = {
                'radius': self.mask_list_radius.value(),
                'variation': self.mask_list_variation.value(),
                'cen': (row, col)
            }
            pos = self.sm.get_pts_with_similar_intensity(**kwargs)
            self.mask_list_add_pts(pos)

    def mask_evaluate(self, target=None):
        if target is None or not self.is_ready():
            return

        if target == 'mask_blemish':
            kwargs = {
                'fname': self.blemish_fname.text(),
                'key': self.blemish_path.text()
            }
        elif target == 'mask_file':
            kwargs = {
                'fname': self.maskfile_fname.text(),
                'key': self.maskfile_path.text()
            }
        elif target == 'mask_list':
            num_row = self.mask_list_xylist.count()
            val = [str(self.mask_list_xylist.item(i).text())
                   for i in range(num_row)]
            val = ' '.join(val)
            xy = text_to_array(val)
            xy = xy[0: xy.size // 2 * 2].reshape(-1, 2).T
            xy = np.roll(xy, shift=1, axis=0)
            kwargs = {
                'zero_loc': xy
            }
        elif target == 'mask_draw':
            kwargs = {
                'arr': np.logical_not(self.sm.apply_drawing())
            }
        elif target == 'mask_threshold':
            kwargs = {
                'low': self.binary_threshold_low.value(),
                'high': self.binary_threshold_high.value(),
                'scale': ['linear', 'log'][self.binary_scale.currentIndex()]
            }
        elif target == 'mask_outlier':
            num = self.outlier_num_roi.value()
            cutoff = self.outlier_cutoff.value()
            # iterations = self.outlier_iterations.value()
            saxs1d, zero_loc = self.sm.compute_saxs1d(num=num, cutoff=cutoff)

            self.mask_outlier_hdl.clear()
            p = self.mask_outlier_hdl
            p.addLegend()
            p.plot(saxs1d[0], saxs1d[1], name='average_ref',
                   pen=pg.mkPen(color='g', width=2))
            p.plot(saxs1d[0], saxs1d[4], name='average_raw',
                   pen=pg.mkPen(color='m', width=2))
            p.plot(saxs1d[0], saxs1d[2], name='cutoff',
                   pen=pg.mkPen(color='b', width=2))
            p.plot(saxs1d[0], saxs1d[3], name='maximum value',
                   pen=pg.mkPen(color='r', width=2))
            p.setLabel('bottom', 'q (Å⁻¹)')
            p.setLabel('left', 'Intensity (a.u.)')
            p.setLogMode(y=True)
            kwargs = {'zero_loc': zero_loc}

        msg = self.sm.mask_evaluate(target, **kwargs)
        self.statusbar.showMessage(msg, 10000)
        self.plot_index.setCurrentIndex(0)
        self.plot_index.setCurrentIndex(5)
        return

    def mask_apply(self, target):
        if not self.is_ready():
            return

        self.sm.mask_apply(target)

        # perform evaluate again so the saxs1d shows the new results;
        if target == 'mask_outlier':
            self.mask_evaluate(target=target)
        elif target == 'mask_list':
            self.mask_list_clear()

        self.plot_index.setCurrentIndex(0)
        self.plot_index.setCurrentIndex(1)

    def update_index(self):
        idx = self.mp1.currentIndex
        self.plot_index.setCurrentIndex(idx)
        # make the mask and preview binary
        if idx in [2, 5]:
            self.mp1.setLevels(0, 1)
 
    def is_ready(self):
        if not self.sm.is_ready():
            self.statusbar.showMessage('No scattering image is loaded.', 500)
            return False
        return True
    
    def update_parameters(self, swapxy=False):
        if not self.is_ready():
            return

        pvs = (self.db_cenx, self.db_ceny, self.db_energy, self.db_pix_dim,
               self.db_det_dist)
        values = []
        for pv in pvs:
            values.append(pv.value())
        if swapxy:
            y, x = values[0], values[1]
            values[0], values[1] = x, y
            self.db_cenx.setValue(x)
            self.db_ceny.setValue(y)
        self.sm.update_parameters(values)
        self.groupBox.repaint()
        self.plot()

    def select_raw(self):
        fname = QFileDialog.getOpenFileName(self,
                                            caption='Select raw file hdf',
                                            directory=self.work_dir
                                            )[0]
        # fname = """
        # /Users/mqichu/Documents/local_dev/pysimplemask/tests/data/
        # E0135_La0p65_L2_013C_att04_Rq0_00001/E0135_La0p65_L2_013C_
        # att04_Rq0_00001_0001-100000.hdf"

        if fname not in [None, '']:
            self.fname.setText(fname)
        return

    def select_blemish(self):
        fname = QFileDialog.getOpenFileName(self, 'Select blemish file')[0]
        if fname not in [None, '']:
            self.blemish_fname.setText(fname)

        if fname.endswith('.tif') or fname.endswith('.tiff'):
            self.blemish_path.setDisabled(True)
        else:
            self.blemish_path.setEnabled(True)

        return

    def select_maskfile(self):
        fname = QFileDialog.getOpenFileName(self, 'Select mask file')[0]
        # fname = "../tests/data/triangle_mask/mask_lambda_test.h5"
        if fname not in [None, '']:
            self.maskfile_fname.setText(fname)
        if fname.endswith('.tif') or fname.endswith('.tiff'):
            self.maskfile_path.setDisabled(True)
        else:
            self.maskfile_path.setEnabled(True)
        return

    def load(self):
        if not os.path.isfile(self.fname.text()):
            self.select_raw()
        if not os.path.isfile(self.fname.text()):
            self.statusbar.showMessage('select a valid file')
            return

        fname = self.fname.text()
        self.sm.read_data(fname)

        self.db_cenx.setValue(self.sm.meta['bcx'])
        self.db_ceny.setValue(self.sm.meta['bcy'])
        self.db_energy.setValue(self.sm.meta['energy'])
        self.db_pix_dim.setValue(self.sm.meta['pix_dim'])
        self.db_det_dist.setValue(self.sm.meta['det_dist'])
        self.le_shape.setText(str(self.sm.shape))
        self.groupBox.repaint()
        self.plot()

    def plot(self):
        kwargs = {
            'cmap': self.plot_cmap.currentText(),
            'log': self.plot_log.isChecked(),
            'invert': self.plot_invert.isChecked(),
            # 'rotate': self.plot_rotate.isChecked(),
            'plot_center': self.plot_center.isChecked(),
        }
        self.sm.show_saxs(**kwargs)
        self.plot_index.setCurrentIndex(0)

    def add_drawing(self):
        if not self.is_ready():
            return
        color = ('g', 'y', 'b', 'r', 'c', 'm', 'k', 'w')[
            self.cb_selector_color.currentIndex()]
        kwargs = {
            'color': color,
            'sl_type': self.cb_selector_type.currentText(),
            'sl_mode': self.cb_selector_mode.currentText(),
            'width': self.plot_width.value()
        }
        self.sm.add_drawing(**kwargs)
        return

    def compute_partition(self):
        if not self.is_ready():
            return

        kwargs = {
            'sq_num': self.sb_sqnum.value(),
            'dq_num': self.sb_dqnum.value(),
            'sp_num': self.sb_spnum.value(),
            'dp_num': self.sb_dpnum.value(),
            'style': self.partition_style.currentText(),
        }
        self.sm.compute_partition(**kwargs)
        self.plot_index.setCurrentIndex(3)

    def save_mask(self):
        if not self.is_ready():
            return

        if self.sm.new_partition is None:
            self.compute_partition()
        save_fname = QFileDialog.getSaveFileName(
            self, caption='Save mask/qmap as')[0]
        self.sm.save_partition(save_fname)

    def mask_list_load(self):
        if not self.is_ready():
            return

        fname = QFileDialog.getOpenFileName(self, 'Select mask file')[0]
        if fname in ['', None]:
            return

        try:
            xy = np.loadtxt(fname, delimiter=',')
        except ValueError:
            xy = np.loadtxt(fname)
        except Exception:
            self.statusbar.showMessage(
                'only support csv and space separated file', 500)
            return

        if self.mask_list_rowcol.isChecked():
            xy = np.roll(xy, shift=1, axis=1)
        if self.mask_list_1based.isChecked():
            xy = xy - 1

        xy = xy.astype(np.int64)
        self.mask_list_add_pts(xy)

    def mask_list_add(self):
        pts = self.mask_list_input.text()
        self.mask_list_input.clear()
        if len(pts) < 1:
            self.statusbar.showMessage('Input list is almost empty.', 500)
            return

        xy = text_to_array(pts)
        xy = xy[0: xy.size // 2 * 2].reshape(-1, 2)
        self.mask_list_add_pts(xy)

    def mask_list_add_pts(self, pts):
        for xy in pts:
            xy_str = str(xy)
            if xy_str not in self.sm.bad_pixel_set:
                self.mask_list_xylist.addItem(xy_str)
                self.sm.bad_pixel_set.add(xy_str)
        self.groupBox_11.setTitle('xy list: %d' % len(self.sm.bad_pixel_set))

    def mask_list_clear(self):
        self.sm.bad_pixel_set.clear()
        self.mask_list_xylist.clear()
        self.groupBox_11.setTitle('xy list')

    def load_last_config(self, ):
        if not os.path.isfile(self.lastconfig_fname):
            logger.info('no configure file found. skip')
            return

        try:
            with open(self.lastconfig_fname, 'r') as fhdl:
                logger.info('load the last configure.')
                config = json.load(fhdl)
                for key, val in config.items():
                    self.__dict__[key].setText(val)
        except Exception:
            os.remove(self.lastconfig_fname)
            logger.info('configuration file damaged. delete it now')
        return

    def closeEvent(self, e) -> None:
        keys = ['blemish_fname', 'blemish_path', 'maskfile_fname',
                'maskfile_path']
        config = {}
        for key in keys:
            config[key] = self.__dict__[key].text()

        with open(self.lastconfig_fname, 'w') as fhdl:
            json.dump(config, fhdl)


def run():
    # if os.name == 'nt':
    #     setup_windows_icon()
    # QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        window = SimpleMaskGUI(sys.argv[1])
    else:
        window = SimpleMaskGUI()
    app.exec_()


if __name__ == '__main__':
    run()
