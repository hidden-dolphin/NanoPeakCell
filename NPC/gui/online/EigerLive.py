from multiprocessing import Process

import pyqtgraph as pg
import zmq
from PyQt4 import  QtGui, QtCore
from NPC.gui.Views import ImageViewOnline, XPView, HitLive, MaxProjViewOnline

from NPC.gui.online.EigerLive_process import loadBalancer, workerEiger

pg.setConfigOptions(imageAxisOrder='row-major')
app = QtGui.QApplication([])
import inspect, time, json , os
import argparse


class LiveMenuBar(QtGui.QMenuBar):
    def __init__(self, parentWidget, controller):
        QtGui.QMenuBar.__init__(self, parentWidget)
        #self.setGeometry(QtCore.QRect(0, 0, 910, 22))
        self.parent = controller
        self.menuFile = self.addMenu("&File")
        self.actionLoad_Mask = self.menuFile.addAction("&Load Mask")
        self.actionLoad_Mask.setShortcut('Ctrl+M')
        #self.actionLoad_Geometry = self.menuFile.addAction("&Load Geometry")
        #self.actionLoad_Geometry.setShortcut('Ctrl+G')
        self.actionSep1 = self.menuFile.addAction("")
        self.actionSep1.setSeparator(True)

        self.actionDelete_Mask = self.menuFile.addAction("&Delete Mask")
        #self.actionDelete_Geom = self.menuFile.addAction("&Delete Geom")
        self.actionSep2 = self.menuFile.addAction("")
        self.actionSep2.setSeparator(True)
        self.actionClose = self.menuFile.addAction("&Close")



        self.menuShow = self.addMenu("&Show")
        self.actionBeam_Center = QtGui.QAction("&Beam Center", self)
        self.actionBeam_Center.setShortcut('Ctrl+B')
        self.actionBeam_Center.setCheckable(True)
        self.actionBeam_Center.setChecked(False)
        self.actionBeam_Center.setIconVisibleInMenu(False)
        self.actionResolution_Rings = QtGui.QAction("&Resolution Rings", self)
        self.actionResolution_Rings.setShortcut('Ctrl+R')
        self.actionResolution_Rings.setCheckable(True)
        self.actionResolution_Rings.setChecked(False)
        self.actionROI = QtGui.QAction("&Region of Interest", self)
        self.actionROI.setShortcut('Ctrl+I')
        self.actionROI.setCheckable(True)
        self.actionROI.setChecked(True)

        self.menuShow.addAction(self.actionBeam_Center)
        self.menuShow.addAction(self.actionResolution_Rings)
        self.menuShow.addAction(self.actionROI)

        self.menuView = self.addMenu("&View")
        self.actionHit_Viewer = QtGui.QAction("&Hit Viewer", self)
        self.actionHit_Viewer.setCheckable(True)
        self.actionHit_Viewer.setChecked(True)
        self.actionExperimental_Settings = QtGui.QAction("&Experimental Settings", self)
        self.actionExperimental_Settings.setCheckable(True)
        self.actionExperimental_Settings.setChecked(True)
        self.actionMaximum_Projection = QtGui.QAction("&Maximum Projection", self)
        self.actionMaximum_Projection.setCheckable(True)
        self.actionMaximum_Projection.setChecked(True)
        self.menuView.addAction(self.actionExperimental_Settings)
        self.menuView.addAction(self.actionHit_Viewer)
        self.menuView.addAction(self.actionMaximum_Projection)

        #self.menuBar.actionLoad_Mask.triggered.connect(lambda: self.openMask(openfn=True))
        #self.menuBar.actionLoad_Geometry.triggered.connect(lambda: self.openGeometry(openfn=True))
        #self.menuBar.actionDelete_Mask.triggered.connect(self.deleteMask)
        #self.menuBar.actionDelete_Geom.triggered.connect(self.deleteGeom)


        self.ViewMenuDict = {'XP': ('actionExperimental_Settings', self.parent.XPView),
                             'HV': ('actionHit_Viewer', self.parent.HitLiveView),
                             'MP': ('actionMaximum_Projection', self.parent.MaxProjView)
                             }

        self.actionClose.triggered.connect(self.parent.closeApp)

        self.actionExperimental_Settings.triggered.connect(lambda: self.toggleView('XP'))
        self.actionHit_Viewer.triggered.connect(lambda: self.toggleView('HV'))
        self.actionMaximum_Projection.triggered.connect(lambda: self.toggleView('MP'))

        self.parent.XPView.hideMe.connect(self.UncheckMenuView)
        self.parent.HitLiveView.hideMe.connect(self.UncheckMenuView)
        self.parent.MaxProjView.hideMe.connect(self.UncheckMenuView)
        self.actionBeam_Center.triggered.connect(self.parent.ImageView.toggleBeamCenter)
        self.actionBeam_Center.triggered.connect(self.parent.MaxProjView.toggleBeamCenter)
        self.actionResolution_Rings.triggered.connect(self.parent.toggleResRings)
        self.actionROI.triggered.connect(lambda: self.parent.toggleROI(False))




    def toggleView(self, key):
        attr, view = self.ViewMenuDict[key]
        if getattr(self, attr).isChecked():
            view.show()
            view.visible = True
            view.move(view.Pos)
        else:
            view.hide()

    #Slots for emitted signals
    def UncheckMenuView(self,attr):
        Qaction = getattr(self,str(attr))
        Qaction.setChecked(False)

class LiveEiGerController(object):

    def __init__(self, app, HF):
        self.app = app
        self.binning = 1
        self.HF = HF


        # The hit view will process results coming from workers (PULL socket @ 5558)
        # The hit view will send parameters to workers (PUB socket @ 5559)
        contextResultsReceiver = zmq.Context()
        self.resultsReceiver = contextResultsReceiver.socket(zmq.PULL)
        self.resultsReceiver.bind("tcp://127.0.0.1:5558")

        contextControlSender = zmq.Context()
        self.controlSender = contextControlSender.socket(zmq.PUB)
        self.controlSender.bind("tcp://127.0.0.1:5559")

        # The Viewer (client) will send request to the Load Balancer @ 5570
        # the Load Balancer will forward the request to an available worker.
        # The given worker send his reply to the load Balancer (an image), which forwards to the Viewer
        # The workers are flagged as available, once they send such message to the Load Balancer (Here "READY")
        imgSocket = zmq.Context().socket(zmq.REQ)
        imgSocket.identity = u"Client-{}".format(0).encode("ascii")
        imgSocket.connect('tcp://localhost:5570')

        maxProjSocket = zmq.Context().socket(zmq.REQ)
        maxProjSocket.identity = u"Client-{}".format(1).encode("ascii")
        maxProjSocket.connect('tcp://localhost:5570')

        self.HitLiveView = HitLive(self, self.resultsReceiver, self.controlSender)
        self.XPView = XPView(True)
        self.ImageView = ImageViewOnline(self.XPView, binning=2, name='ImageView', zmqSocket = imgSocket, req = "HIT", timeout = 250)
        #XPView, binning, name, imgSocket, req, timeout
        self.ImageView.setWindowTitle("NPC - Frames")
        self.MaxProjView = MaxProjViewOnline(self.XPView, binning=1, name='MaxProj', zmqSocket=maxProjSocket, req = "MAXPROJ", timeout = 2000)
        self.MaxProjView.setWindowTitle("NPC - Maximum Projection")

        self.menuBar = LiveMenuBar(self.ImageView, self)
        self.menuBar.setGeometry(QtCore.QRect(0, 0, 1060, 22))
        self.ImageView.setMenuBar(self.menuBar)
        self.menuBar.setNativeMenuBar(False)
        self.MaxProjView.view.roi.show()
        self.ImageView.view.roi.show()

        self.ImageView.closeSignal.connect(self.closeApp)
        self.HitLiveView.ui.ShowROI.clicked.connect(lambda: self.toggleROI(True))
        self.ImageView.view.roi.sigDragFinished.connect(self.MaxProjView.view.roi.setPosNSize)
        self.MaxProjView.view.roi.sigDragFinished.connect(self.ImageView.view.roi.setPosNSize)
        self.ImageView.view.roi.sigDragFinished.connect(self.HitLiveView.setROI)
        self.MaxProjView.view.roi.sigDragFinished.connect(self.HitLiveView.setROI)

        self.HitLiveView.sigUpdateROI.connect(self.ImageView.view.roi.setPosNSize)
        self.HitLiveView.sigUpdateROI.connect(self.MaxProjView.view.roi.setPosNSize)
        self.MaxProjView.sigResetMP.connect(self.HitLiveView.sendResetMP)

        self.views = [self.ImageView, self.XPView, self.HitLiveView, self.MaxProjView]

        self.restoreState()

        Process(target=loadBalancer, args=(self.HF,)).start()

    def toggleResRings(self):
        if not self.ImageView.toggleResRings():
            self.menuBar.actionResolution_Rings.setChecked(False)
        else:
            self.MaxProjView.toggleResRings()

    def toggleBeamCenter(self):
        if not self.ImageView.toggleBeamCenter():
            self.menuBar.actionBeam_Center.setChecked(False)

    def toggleROI(self, updateMenu=False):
        self.ImageView.view.roi.updateVisible()
        self.MaxProjView.view.roi.updateVisible()
        self.HitLiveView.setLabel()
        if updateMenu:
            if self.menuBar.actionROI.isChecked():
                self.menuBar.actionROI.setChecked(False)
            else:
                self.menuBar.actionROI.setChecked(True)

    def closeApp(self):
        self.saveState()
        for view in [self.XPView, self.HitLiveView, self.MaxProjView]:
            view.close()
        self.controlSender.send_json({b"STOP" : "STOP" })
        time.sleep(1)
        self.controlSender.close()
        self.resultsReceiver.close()
        time.sleep(1)
        self.app.quit()

    def saveState(self):
        views = [self.XPView, self.ImageView, self.HitLiveView, self.MaxProjView]
        settings = {}

        for i in range(len(views)):
            view = views[i]
            s = view.size()
            pos = view.pos()
            d = {'height': int(s.height()),
                 'width': int(s.width()),
                 'x': int(pos.x()),
                 'y': int(pos.y()),
                 'visible': view.visible,
                 }

            for name, obj in inspect.getmembers(view.ui):
                # if type(obj) is QComboBox:  # this works similar to isinstance, but missed some field... not sure why?
                if isinstance(obj, QtGui.QComboBox):
                    name = obj.objectName()  # get combobox name
                    index = obj.currentIndex()  # get current index from combobox
                    text = obj.itemText(index)  # get the text for current index
                    d[str(name)] = str(text)

                if isinstance(obj, QtGui.QLineEdit):
                    name = obj.objectName()
                    value = obj.text()
                    d[str(name)] = str(value)

                if isinstance(obj, QtGui.QCheckBox):
                    name = obj.objectName()
                    state = obj.isChecked()
                    d[str(name)] = state

                if isinstance(obj, QtGui.QRadioButton):
                    name = obj.objectName()
                    value = obj.isChecked()  # get stored value from registry
                    d[str(name)] = value

            settings[view.name] = d

        try:
            settings['maskFN'] = self.maskFile
        except:
            settings['maskFN'] = ""

        with open(os.path.expanduser('~/.NPGLiverc.json'), 'w') as outfile:
            json.dump(settings, outfile)

    def restoreState(self):
        views = [self.XPView, self.ImageView, self.HitLiveView, self.MaxProjView]
        menus = [self.menuBar.actionExperimental_Settings, None, self.menuBar.actionHit_Viewer,
                 self.menuBar.actionMaximum_Projection]
        jsonFile = os.path.expanduser('~/.NPGLiverc.json')

        if os.path.exists(jsonFile):
            settings = json.loads(open(jsonFile).read())
        else:
            return

        for i in range(len(views)):
            view = views[i]
            try:
                viewSettings = settings[view.name]
            except KeyError:
                continue

            # Restore geometry
            view.move(int(viewSettings['x']), int(viewSettings['y']))
            view.resize(int(viewSettings['width']), int(viewSettings['height']))
            view.Pos = view.pos()

            # Was the window visible or not ?
            vis = viewSettings['visible']
            view.setVisible(vis)
            view.visible = vis
            # Restore menu state
            menu = menus[i]
            if menu is not None:
                menu.setChecked(vis)

            for name, obj in inspect.getmembers(view.ui):
                if isinstance(obj, QtGui.QComboBox):
                    #index = obj.currentIndex()  # get current region from combobox
                    name = obj.objectName()
                    value = viewSettings[str(name)]

                    if value == "":
                        continue
                    index = obj.findText(value)  # get the corresponding index for specified string in combobox
                    if index == -1:  # add to list if not found
                        obj.insertItems(0, [value])
                        index = obj.findText(value)
                        obj.setCurrentIndex(index)
                    else:
                        obj.setCurrentIndex(index)  # preselect a combobox value by index

                if isinstance(obj, QtGui.QLineEdit):
                    name = obj.objectName()
                    value = viewSettings[str(name)]
                    try:
                        obj.setText(value)  # restore lineEditFile
                    except TypeError:
                        continue

                if isinstance(obj, QtGui.QCheckBox):
                    name = obj.objectName()
                    value = viewSettings[str(name)]
                    if value != None:
                        obj.setChecked(value)  # restore checkbox

                if isinstance(obj, QtGui.QRadioButton):
                    name = obj.objectName()
                    value = viewSettings[str(name)]

                    if value != None:
                        obj.setDown(value)

        # Do not forget to restore the object attributes to the widget values.
        self.ImageView.setAttr()
        self.MaxProjView.setAttr()
        self.XPView.setupData()
        self.HitLiveView.getROI()

        if self.HF.threshold == None:
            print("Restoring Threshold Value from previous run")
            self.HF.threshold = int(self.HitLiveView.ui.thresh.text())
        else:
            print("Setting Threshold Value from command line to %i " %self.HF.threshold)
            self.HitLiveView.ui.thresh.setText(str(self.HF.threshold))
        if self.HF.npixels == None:
            print("Restoring NPixels Value from previous run")
            self.HF.npixels = int(self.HitLiveView.ui.npix.text())
        else:
            print("Setting NPixels Value from command line to %i" %self.HF.npixels)
            self.HitLiveView.ui.npix.setText(str(self.HF.npixels))

        self.HF.x1 = int(self.HitLiveView.ui.ROIX1.text())
        self.HF.x2 = int(self.HitLiveView.ui.ROIX2.text())
        self.HF.y1 = int(self.HitLiveView.ui.ROIY1.text())
        self.HF.y2 = int(self.HitLiveView.ui.ROIY2.text())

        if self.HF.maskFN == None:
            print("Restoring Mask File from previous run")
            try:
                self.maskFile = settings['maskFN']
            except KeyError:
                self.maskFile = ""
        else:
            if self.HF.maskFN is not None:
                print("Setting Mask File from command line: %s" %self.HF.maskFN)
                self.maskFile = self.HF.maskFN
            else:
                self.maskFile = ""

        if self.maskFile:
            self.HF.maskFN = self.maskFile
            self.ImageView.ui.Mask.setText(
                "Current Mask File:  %s " % self.maskFile)
            self.MaxProjView.ui.Mask.setText(
                "Current Mask File:  %s " % self.maskFile)
            self.ImageView.ui.Geom.setText("")
            self.MaxProjView.ui.Geom.setText("")

class HitFinderParameters(object):

    def __init__(self, args):

        self.threshold = args.threshold
        self.npixels = args.npixels
        self.maskFN = args.maskFN
        self.ip = args.ip

        self.x1 = 0
        self.y1 = 0
        self.x2 = 2167
        self.y2 = 2070
        self.roi = [self.x1, self.y1, self.x2, self.y2]
        self.RADDAM = False
        self.NShots = 0
        self.STOP = 0
        self.mask = None


        try:
            self.ip = args['ip'][0]
        except TypeError:
            self.ip = None


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        desc = """
        """

        argparse.ArgumentParser.__init__(self, description=desc)
        self.add_argument("-n","--cpus", nargs=1, type=int, default=[4],
                       help="number of workers (default 4)")
        self.add_argument("-t", "--threshold", nargs=1, type=int, default= [None],
                          help="threshold used for hit finding (optional)")
        self.add_argument("-p", "--pixels", nargs=1, default=[None], type=int,
                       help="Number of pixels above threshold needed to consider a hit (optional)")
        self.add_argument("-m","--mask", nargs= 1, type= str, default= [None],
                       help="Mask to be used (optional)")
        self.add_argument("-ip","--ip", nargs= 1, type= str, default= [None],
                       help="Eiger IP address")

        self.args = self.parse_args()

    def _check_input(self):
        if self.args.ip == None:
            print("Sorry: the ip address of the detector is required")
            return False
        else:
            self.cpus = self.args.cpus[0]
            self.ip = self.args.ip[0]
            self.threshold = self.args.threshold[0]
            self.npixels = self.args.pixels[0]
            self.maskFN = self.args.mask[0]
            return True
            # Here should check the ip address

            #
            #try:
            #    apiVersionReq = requests.get("http://%s/detector/api/<api-version>/description" % self.ip, timeout = 1)
            #    if apiVersionReq.status_code == "200":
            #        print("Communication with detector OK")
            #        self.apiVersion = apiVersionReq.json()["value"]
            #        detReq = requests.get("http://%s/detector/api/<api-version>/description" % self.ip, timeout = 1)
            #        self.detector = detReq.json()["value"]
            #    else:
            #        e = 1

            #except requests.ConnectionError:
            #    e = 1

            #if e:
            #    print(
            #        "Communication with the Eiger detector @ %s impossible.\nPlease check the ip adress or detector status.\n" % self.ip)
            #    return False


if __name__ == '__main__':
    import sys
    parser = ArgumentParser()
    if parser._check_input():

        HF = HitFinderParameters(parser)
        worker_pool = range(parser.cpus)
        for wrk_num in range(len(worker_pool)):
            Process(target=workerEiger, args=(wrk_num,HF)).start()

        #Process(target=ventilator, args=()).start()
        myapp = LiveEiGerController(app, HF)
        sys.exit(app.exec_())
    else:
        parser.print_usage()

