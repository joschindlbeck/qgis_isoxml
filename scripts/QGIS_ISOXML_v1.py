# -*- coding: utf-8 -*-

"""
   05.03.23, joschindlbeck
   This script transforms a vector layer in QGIS with polygons to a ISO_XML Tasks file 

"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterCrs,
                       QgsProcessingMultiStepFeedback,
                       QgsProcessingParameterMapLayer,
                       QgsProcessingParameterNumber,
                       QgsMapLayer,
                       QgsProcessingParameterString,
                       QgsCoordinateReferenceSystem,
                       QgsProcessingUtils,
                       QgsCoordinateReferenceSystem,
                       QgsProject,
                       QgsCoordinateTransform,
                       QgsFeature,
                       QgsGeometry)
from qgis import processing
from math import cos
from qgis.PyQt.QtGui import QColor
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import tostring


class IsoXmlTaskFileCreator(QgsProcessingAlgorithm):
    """
    Test: Create ISO XML Task file out of vector layer
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.
    INPUT_FIELD_BOUNDARY = 'Feldgrenzen'
    INPUT_ATTRIBUTE_FIELDNAME = 'Feldname'
    INPUT_GRID_LARGE = 'Gittergrob'
    INPUT_WEED_LAYER = 'Unkrautflchen'
    INPUT_COLOR = 'Color'
    INPUT_GRID_CRS = 'GridCrs'
    OUTPUT_SECTIONS_LAYER = 'Sections_joined'

    INPUT = 'INPUT'
    OUTPUT_TASKDATA_FILE = 'OUTPUT_TASKDATA_FILE'
    OUTPUT_PROJECTED_LAYER = 'OUTPUT_PROJECTED_LAYER'
    INPUT_FIELDS_FILE = 'INPUT_FIELDS_FILE'

    mPerDegreeLat = 0.0
    mPerDegreeLon = 0.0
    latStart = 48.9636327590282  # default start latitude
    lonStart = 12.1934211840036  # default start longitude
    count = 0

    # Reference systems
    srcCRS = QgsCoordinateReferenceSystem(4326)
    destCRS = QgsCoordinateReferenceSystem(4326)
    crsConversionNeeded = False
    crsTransform = None

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return IsoXmlTaskFileCreator()

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'IsoXmlTaskFileCreator'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Test ISO XML')

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr('ISOXML')

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'isoxml'

    def shortHelpString(self):
        """
        Returns a localised short helper string for the algorithm. This string
        should provide a basic description about what the algorithm does and the
        parameters and outputs associated with it..
        """
        helptext = '''
        TODO - adjust!! <br>
        Create Section file for AGOpenGPS, v2<br>
        <p>09.04.2022, joschindlbeck</p>
        <a href=https://github.com/joschindlbeck/aog_qgis>Github</a>
        Expected Input:
        <b>Field Boundary</b>: Vector Layer with a polygon representing the field boundary. A vector layer generated from Field.kml from AGOOpenGPS works best
        <b>Layer with weeds</b>: Vector Layer with multiple polygons representing the weed spots that shall be applied in AGOpenGPS; the script will mark all other areas within the field boundaries as already applied
        <b>Grid size small / large</b>: To fill the applied areas, the script will generate a grid / quadrats of two different sizes; the size can be entered, however the large size must be a multiple of the small size
        <b>Grid CRS</b>: For the grid calculation, we need a non geographic CRS
        <b>AOG Fields file</b>: Path to the AOG Fields.txt file; this is needed to get the base coordinates that AOG uses internally
        <b>Applied Sections Color</b>: The color to be used for the section patches in AOG that are already applied
        <b>Sections Layer</b>: This is the output layer of the script operation and represents the already applied area for AOG
        <b>Sections.txt file output</b>: Path to the AOG sections file that will be written
        '''

        return helptext

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        # -- Input
        # Vector layer with fields
        self.addParameter(QgsProcessingParameterMapLayer(self.INPUT_FIELD_BOUNDARY, self.tr(
            'Field Boundaries'), defaultValue=None, types=[QgsProcessing.TypeVectorPolygon]))
        # Attribute for field name
        self.addParameter(QgsProcessingParameterString(self.INPUT_ATTRIBUTE_FIELDNAME, self.tr('Attribute Name for Field Name'),defaultValue="Name"))    

        # -- Output
        # Output File destination for TASKDATA.XML
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_TASKDATA_FILE, "TASKDATA.XML file output"))

    def processAlgorithm(self, parameters, context, model_feedback):
        """
        Here is where the processing itself takes place.
        """
        feedback = QgsProcessingMultiStepFeedback(8, model_feedback)
        results = {}
        outputs = {}

        # Load Input layer
        input_featuresource = self.parameterAsSource(
            parameters, self.INPUT_FIELD_BOUNDARY, context)

        # output file
        file = self.parameterAsFileOutput(
            parameters, self.OUTPUT_TASKDATA_FILE, context)

        # Attribute name for Field names
        fieldNameAttrName = self.parameterAsString(parameters, self.INPUT_ATTRIBUTE_FIELDNAME, context)

        # If sink was not created, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSinkError method to return a standard
        # helper text for when a sink cannot be evaluated
        if file is None:
            raise QgsProcessingException(self.invalidSinkError(
                parameters, self.OUTPUT_TASKDATA_FILE))
        # Compute the number of steps to display within the progress bar and
        # get features fromsource
        total = 100.0 / input_featuresource.featureCount() if input_featuresource.featureCount() else 0

        if input_featuresource.sourceCrs().authid != QgsCoordinateReferenceSystem(4326).authid:
            feedback.pushInfo("CRS Transformation necessary")
            transformedLayer = self.reprojectLayer(parameters, outputs,context, feedback)
            # get features from transformed layer
            features = transformedLayer.getFeatures()
        else:
            # get features from input
            features = input_featuresource.getFeatures()

        feedback.pushInfo("Writing TASKDATA file...")
        # get taskdata xml element
        taskdata = self.createTaskXML()
        with open(file, "w") as output_file:
            for current, feature in enumerate(features):
                # Stop the algorithm if cancel button has been clicked
                if feedback.isCanceled():
                    # break
                    exit()
                feature: QgsFeature = feature
                # Get feature geometry
                if feature.hasGeometry():
                    geometry: QgsGeometry = feature.geometry()
                    if self.crsConversionNeeded:
                        result = geometry.transform(self.crsTransform)
                        feedback.pushInfo("Transformation Result: "+str(result))

                    # create partfield
                    if feature.attribute(fieldNameAttrName) is not None:
                        name = str(feature.attribute(fieldNameAttrName))
                    else:
                        name = "Feld-{i}".format(i=current)
                    pfd = ET.SubElement(taskdata, "PFD", {"A":"PFD-{i}".format(i=current), "B":"", "C": name, "D":"1"})
                    pln = ET.SubElement(pfd, "PLN", {"A":"1"})
                    lsg = ET.SubElement(pln, "LSG", {"A":"1"})
                    for currentVertice, vertice in enumerate(geometry.vertices()):
                        #output_file.write(
                        #    str(vertice.y()) + "," + str(vertice.x())+"\n")
                        ET.SubElement(lsg, "PNT",{"A":"2", "C": str(vertice.y()), "D": str(vertice.x())})

                # Update the progress bar
                feedback.setProgress(int(current * total))
            # write file
            output_file.write('<?xml version="1.0" encoding="UTF-8"?>')
            output_file.write(tostring(taskdata, encoding="unicode"))
            #et = ET.ElementTree(taskdata)
            #et.write(output_file,encoding='utf-8', xml_declaration=True)

        # add Section file output to results
        results[self.OUTPUT_TASKDATA_FILE] = file
        # return results
        return results

    '''
    XML Processinmg
    '''

    def createTaskXML(self):
        taskdata = ET.Element("ISO11783_TaskData", {"VersionMajor": "3", "VersionMinor": "3",
                              "ManagementSoftwareManufacturer": "", "ManagementSoftwareVersion": "", "DataTransferOrigin": "1"})
        return taskdata

    '''
    Reproject Layer to WGS84
    '''
    def reprojectLayer(self, parameters, outputs, context, feedback ) -> QgsMapLayer:
         # Reproject layer
        alg_params = {
            'INPUT': parameters[self.INPUT_FIELD_BOUNDARY],
            'OPERATION': '',
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326'),
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ReprojectLayer'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        layerpath = outputs['ReprojectLayer']['OUTPUT']
        return QgsProcessingUtils.mapLayerFromString(layerpath, context)