'''
Copyright 2024 Esri
Licensed under the Apache License Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
     http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''
# -*- coding: utf-8 -*-
import arcpy, os
import re
from arcpy import env
class CreateSchemaItems(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Create LRS in Address Data Management solution"
        self.description = "Configure an LRS from the Address Data Management solution where only the centerline is present, so that all the required LRS schema are created correctly and the LRS is configured."
        self.canRunInBackground = False
    def getParameterInfo(self):
        """Define parameter definitions"""
        # Geodatabase Parameter
        params = []
        param0 = arcpy.Parameter(
            displayName="Feature Dataset",
            name="in_feature_dataset",
            datatype="DEFeatureDataset",
            parameterType="Required",
            direction="Input")
        params.append(param0)
        
        # LRS Name Parameter
        param1 = arcpy.Parameter(
            displayName="LRS Name",
            name="in_lrs_name",
            datatype="String",
            parameterType="Required",
            direction="Input")
        params.append(param1)
        
        # Derived Output Parameter
        param2 = arcpy.Parameter(
            displayName="LRS Workspace",
            name="out_lrs_workspace",
            datatype="DEWorkspace",
            parameterType="Derived",
            direction="Output")
        
        params.append(param2)
        
        return params
    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True
    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return
    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        # FeatureDataset parameter
        featureDatasetPath = parameters[0].valueAsText
        
        if parameters[0].altered:
            if not arcpy.Exists(featureDatasetPath):
                parameters[0].setErrorMessage("The feature dataset does not exist at the specified location.")
                return
                
            lrsDataset = GetLRSDataset(featureDatasetPath)
            if lrsDataset is not None:
                parameters[0].setErrorMessage("The feature dataset already contains an LRS.")
                return

            roadCenterlineFC = featureDatasetPath + '\\' + 'RoadCenterline'
            if not arcpy.Exists(roadCenterlineFC):
                parameters[0].setErrorMessage("The feature dataset does not contain a RoadCenterline feature class.")
                return
            else:
                clid_field = "cl_id"
                field_list = [field.name for field in arcpy.ListFields(roadCenterlineFC)]
                if clid_field not in field_list:
                    parameters[0].setErrorMessage("The RoadCenterline feature class does not contain a cl_id field.")
                    return
            
            # Update the derived output parameter
            workspacePath = os.path.dirname(featureDatasetPath)
            parameters[2].value = workspacePath
                    
        if parameters[1].altered:
            lrsName = parameters[1].valueAsText
            pattern = r'^[a-zA-Z0-9_\- ]+$'
            match = re.search(pattern, lrsName)
            
            if lrsName[0] == " ":
                parameters[1].setErrorMessage("The specified name cannot start with a space.")
            elif not match:
                parameters[1].setErrorMessage("The specified name contains special characters (except space, -, _).")
            elif len(lrsName) > 32:
                parameters[1].setErrorMessage("The specified name exceeds maximum length of 32.")

        return
    def execute(self, parameters, messages):
        """The source code of the tool."""
        #arcpy.SetupDebugger()
        # FeatureDataset
        featureDatasetPath = parameters[0].valueAsText
        
        featureDatasetName = featureDatasetPath.split('\\')[-1]
        featureDataset = featureDatasetPath + '\\' + featureDatasetName

        # Spatial Reference
        sr = arcpy.Describe(featureDatasetPath).spatialReference

        workspacePath = os.path.dirname(featureDatasetPath)
        workspaceDir = os.path.dirname(workspacePath)
        
        roadCenterlineFC = featureDatasetPath + '\\' + 'RoadCenterline'
        desc = arcpy.Describe(roadCenterlineFC)
        isBranchVersioned = desc.isBranchVersioned

        passFail = ["Pass"]
        
        # Create the Redline feature class.
        arcpy.SetProgressorLabel("Creating Redline feature class")
        path = featureDatasetPath + '\\' + 'Redline'
        redline_feature_class = CreateRedlineFeatureClass(path, sr, isBranchVersioned, passFail)
        if passFail[0] == "Fail":
            arcpy.AddError("The Redline feature class already exists in the feature dataset. Verify that an LRS doesn't already exist.")
            return
        if redline_feature_class is None:
            return
        
        # Create the Calibration Point feature class.
        arcpy.SetProgressorLabel("Creating Calibration_Point feature class")
        path = featureDatasetPath + '\\' + 'Calibration_Point'
        calibration_point_feature_class = CreateCalibrationPointFeatureClass(path, sr, isBranchVersioned, passFail)
        if passFail[0] == "Fail":
            arcpy.AddError("The Calibration_Point feature class already exists in the feature dataset. Verify that an LRS doesn't already exist.")
            return
        if calibration_point_feature_class is None:
            return

        # Create the Centerline Sequence table.
        arcpy.SetProgressorLabel("Creating Centerline_Sequence table")
        path = workspacePath + '\\' + 'Centerline_Sequence'
        centerline_sequence_table = CreateCenterlineSequenceTable(path, sr, isBranchVersioned, passFail)
        if passFail[0] == "Fail":
            arcpy.AddError("The Centerline_Sequence table already exists in the feature dataset. Verify that an LRS doesn't already exist.")
            return
        if centerline_sequence_table is None:
            return
        
        # Create the LRS
        arcpy.SetProgressorLabel("Creating LRS")
        lrsName = parameters[1].valueAsText
        path = featureDatasetPath + '\\' + lrsName
        CreateLRS(workspacePath, path, centerline_sequence_table, calibration_point_feature_class, redline_feature_class)
        
        return
    
##******************************************##
##            Utility Functions             ##
##******************************************##

def CreateRedlineFeatureClass(out_path_and_name, sr, isBranchVersioned, passFail):
    
    featureDatasetPath = os.path.dirname(out_path_and_name)
    fileName = out_path_and_name.split('\\')[-1]
    
    redlineFeatureClass = featureDatasetPath + "\\" + fileName
    
    if arcpy.Exists(redlineFeatureClass):
        passFail[0] = "Fail"
        return

    # Check for m and z awareness.
    hasZ = "ENABLED"
    hasM = "DISABLED"

    # Create Feature Class.
    try:
        arcpy.management.CreateFeatureclass(featureDatasetPath, fileName, "POLYLINE", None, 
                                hasM, hasZ, sr)
    except BaseException:
        arcpy.AddError("Could not create Redline feature class. Verify that you have at least a Standard license level in Pro to work with this data.")
        return
    
    # Add fields to the Redline feature class.
    arcpy.management.AddField(redlineFeatureClass, "FromMeasure", "DOUBLE", field_length=8, field_is_nullable="NULLABLE")
    arcpy.management.AddField(redlineFeatureClass, "ToMeasure", "DOUBLE", field_length=8, field_is_nullable="NULLABLE")
    arcpy.management.AddField(redlineFeatureClass, "RouteId", "TEXT", field_length=255, field_is_nullable="NULLABLE")
    arcpy.management.AddField(redlineFeatureClass, "RouteName", "TEXT", field_length=38, field_is_nullable="NULLABLE")
    arcpy.management.AddField(redlineFeatureClass, "EffectiveDate", "DATE", field_is_nullable="NULLABLE")
    arcpy.management.AddField(redlineFeatureClass, "ActivityType", "SHORT", field_is_nullable="NULLABLE")
    arcpy.management.AddField(redlineFeatureClass, "NetworkId", "SHORT", field_is_nullable="NULLABLE")
    
    if isBranchVersioned:
        arcpy.management.AddGlobalIDs(redlineFeatureClass)
        arcpy.management.EnableEditorTracking(redlineFeatureClass, "created_user", "created_date", "last_edited_user", "last_edited_date",
                                                add_fields=True)

    # Return path to the feature class.
    return redlineFeatureClass

def CreateCalibrationPointFeatureClass(out_path_and_name, sr, isBranchVersioned, passFail):
    
    featureDatasetPath = os.path.dirname(out_path_and_name)
    fileName = out_path_and_name.split('\\')[-1]
    
    calibrationPointFeatureClass = featureDatasetPath + "\\" + fileName
    if arcpy.Exists(calibrationPointFeatureClass):
        passFail[0] = "Fail"
        return

    # Check for m and z awareness.
    hasZ = "ENABLED"
    hasM = "DISABLED"

    # Create Feature Class.
    try:
        arcpy.management.CreateFeatureclass(featureDatasetPath, fileName, "POINT", None, 
                                hasM, hasZ, sr)
    except BaseException:
        arcpy.AddError("Could not create CalibrationPoint feature class. Verify that you have at least a Standard license level in Pro to work with this data.")
        return
    
    # Add fields to the Calibration Point feature class.
    arcpy.management.AddField(calibrationPointFeatureClass, "FromDate", "DATE", field_is_nullable="NULLABLE")
    arcpy.management.AddField(calibrationPointFeatureClass, "ToDate", "DATE", field_is_nullable="NULLABLE")
    arcpy.management.AddField(calibrationPointFeatureClass, "RouteId", "TEXT", field_length=255, field_is_nullable="NULLABLE")
    arcpy.management.AddField(calibrationPointFeatureClass, "NetworkId", "SHORT", field_is_nullable="NULLABLE")
    arcpy.management.AddField(calibrationPointFeatureClass, "Measure", "DOUBLE", field_is_nullable="NULLABLE")
    
    if isBranchVersioned:
        arcpy.management.AddGlobalIDs(calibrationPointFeatureClass)
        arcpy.management.EnableEditorTracking(calibrationPointFeatureClass, "created_user", "created_date", "last_edited_user", "last_edited_date",
                                                add_fields=True)

    # Return path to the feature class.
    return calibrationPointFeatureClass

def CreateCenterlineSequenceTable(out_path_and_name, sr, isBranchVersioned, passFail):
    
    workspaceDir = os.path.dirname(out_path_and_name)
    fileName = out_path_and_name.split('\\')[-1]
    
    centerlineSequenceTable = workspaceDir + "\\" + fileName
    
    if arcpy.Exists(centerlineSequenceTable):
        passFail[0] = "Fail"
        return

    # Check for m and z awareness.
    hasZ = "ENABLED"
    hasM = "DISABLED"

    # Create Table.
    arcpy.management.CreateTable(workspaceDir, fileName)
    
    try:
        arcpy.management.CreateTable(workspaceDir, fileName)
    except BaseException:
        arcpy.AddError("Could not create CenterlineSequence table.")
        return

    # Add fields to the Calibration Point feature class.
    arcpy.management.AddField(centerlineSequenceTable, "FromDate", "DATE", field_is_nullable="NULLABLE")
    arcpy.management.AddField(centerlineSequenceTable, "ToDate", "DATE", field_is_nullable="NULLABLE")
    arcpy.management.AddField(centerlineSequenceTable, "NetworkId", "SHORT", field_is_nullable="NULLABLE")
    arcpy.management.AddField(centerlineSequenceTable, "RouteId", "TEXT", field_length=255, field_is_nullable="NULLABLE")
    arcpy.management.AddField(centerlineSequenceTable, "CenterlineId", "GUID", field_is_nullable="NULLABLE")
    
    if isBranchVersioned:
        arcpy.management.AddGlobalIDs(centerlineSequenceTable)
        arcpy.management.EnableEditorTracking(centerlineSequenceTable, "created_user", "created_date", "last_edited_user", "last_edited_date",
                                                add_fields=True)

    # Return path to the table.
    return centerlineSequenceTable

def CreateLRS(workspacePath, out_path_and_name, centerline_sequence_table, calibration_point_feature_class, redline_feature_class):
    featureDatasetPath = os.path.dirname(out_path_and_name)
    lrs_name = out_path_and_name.split('\\')[-1]
    centerline_feature_class = featureDatasetPath + "\\" + "RoadCenterline"
    centerline_centerline_id_field = "cl_id"
    centerline_sequence_centerline_id_field = "CenterlineId"
    centerline_sequence_route_id_field = "RouteId"
    centerline_sequence_from_date_field = "FromDate"
    centerline_sequence_to_date_field = "ToDate"
    centerline_sequence_network_id_field = "NetworkId"
    calibration_point_measure_field = "Measure"
    calibration_point_from_date_field = "FromDate"
    calibration_point_to_date_field = "ToDate"
    calibration_point_route_id_field = "RouteId"
    calibration_point_network_id_field = "NetworkId"
    redline_from_measure_field = "FromMeasure"
    redline_to_measure_field = "ToMeasure"
    redline_route_id_field = "RouteId"
    redline_route_name_field = "RouteName"
    redline_effective_date_field = "EffectiveDate"
    redline_activity_type_field = "ActivityType"
    redline_network_id_field = "NetworkId"
    
    # Set current workspace
    arcpy.env.workspace = workspacePath
    
    # Check out license
    arcpy.CheckOutExtension("LocationReferencing")

    try:
        arcpy.locref.CreateLRSFromExistingDataset(lrs_name, centerline_feature_class, centerline_centerline_id_field, centerline_sequence_table, 
                                              centerline_sequence_centerline_id_field, centerline_sequence_route_id_field, 
                                              centerline_sequence_from_date_field, centerline_sequence_to_date_field, 
                                              centerline_sequence_network_id_field, calibration_point_feature_class, 
                                              calibration_point_measure_field, calibration_point_from_date_field, 
                                              calibration_point_to_date_field, calibration_point_route_id_field, 
                                              calibration_point_network_id_field, redline_feature_class, redline_from_measure_field, 
                                              redline_to_measure_field, redline_route_id_field, redline_route_name_field, 
                                              redline_effective_date_field, redline_activity_type_field, redline_network_id_field)
    except BaseException:
        arcpy.AddError("Could not create LRS dataset.")

    # Check in license
    arcpy.CheckInExtension('LocationReferencing')

def GetLRSDataset(featureDatasetPath):
    # Returns the LRS Feature Dataset
    workspaceDir = os.path.dirname(featureDatasetPath)
    workspacePath = arcpy.Describe(workspaceDir).catalogPath

    # Set the environment variable
    arcpy.env.workspace = workspacePath

    # Get the datasets
    datasets = arcpy.ListDatasets()

    for dataset in datasets:
        datasetPath = arcpy.Describe(dataset).catalogPath
        datasetName = datasetPath.split('\\')[-1]
            
        try:
            desc = arcpy.Describe(datasetPath + '\\' + datasetName)
        except BaseException:
            continue

        lrsMetadata = desc.LrsMetadata
        if lrsMetadata:
            return dataset

    return None

    
