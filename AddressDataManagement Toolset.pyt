import arcpy, CreateSchemaItems
import importlib
importlib.reload(CreateSchemaItems)
from CreateSchemaItems import *

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "AddressDataManagement Toolset"
        self.alias = "AddressDataManagementToolset"

        # List of tool classes associated with this toolbox
        self.tools = [CreateSchemaItems]
