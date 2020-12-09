#
## Licensed to the .NET Foundation under one or more agreements.
## The .NET Foundation licenses this file to you under the MIT license.
#
#
#USAGE:
#Add Events: modify <root>src/vm/ClrEtwAll.man
#Look at the Code in  <root>/src/scripts/genLttngProvider.py for using subroutines in this file
#

# Python 2 compatibility
from __future__ import print_function

import os
import xml.dom.minidom as DOM
from utilities import open_for_update

stdprolog="""
// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

/******************************************************************

DO NOT MODIFY. AUTOGENERATED FILE.
This file is generated using the logic from <root>/src/scripts/genEventing.py

******************************************************************/
"""

lindent = "    ";
palDataTypeMapping ={
        #constructed types
        "win:null"          :" ",
        "win:Int64"         :"const __int64",
        "win:ULong"         :"const ULONG",
        "win:count"         :"*",
        "win:Struct"        :"const void",
        #actual spec
        "win:GUID"          :"const GUID",
        "win:AnsiString"    :"LPCSTR",
        "win:UnicodeString" :"PCWSTR",
        "win:Double"        :"const double",
        "win:Int32"         :"const signed int",
        "win:Boolean"       :"const BOOL",
        "win:UInt64"        :"const unsigned __int64",
        "win:UInt32"        :"const unsigned int",
        "win:UInt16"        :"const unsigned short",
        "win:UInt8"         :"const unsigned char",
        "win:Pointer"       :"const void*",
        "win:Binary"        :"const BYTE"
        }
# A Template represents an ETW template can contain 1 or more AbstractTemplates
# The AbstractTemplate contains FunctionSignature
# FunctionSignature consist of FunctionParameter representing each parameter in it's signature

def getParamSequenceSize(paramSequence, estimate):
    total = 0
    pointers = 0
    for param in paramSequence:
        if param == "win:Int64":
            total += 8
        elif param == "win:ULong":
            total += 4
        elif param == "GUID":
            total += 16
        elif param == "win:Double":
            total += 8
        elif param == "win:Int32":
            total += 4
        elif param == "win:Boolean":
            total += 4
        elif param == "win:UInt64":
            total += 8
        elif param == "win:UInt32":
            total += 4
        elif param == "win:UInt16":
            total += 2
        elif param == "win:UInt8":
            total += 1
        elif param == "win:Pointer":
            if estimate:
                total += 8
            else:
                pointers += 1
        elif param == "win:Binary":
            total += 1
        elif estimate:
            if param == "win:AnsiString":
                total += 32
            elif param == "win:UnicodeString":
                total += 64
            elif param == "win:Struct":
                total += 32
        else:
            raise Exception("Don't know size for " + param)

    if estimate:
        return total

    return total, pointers


class Template:
    def __repr__(self):
        return "<Template " + self.name + ">"

    def __init__(self, templateName, fnPrototypes, dependencies, structSizes, arrays):
        self.name = templateName
        self.signature = FunctionSignature()
        self.structs = structSizes
        self.arrays = arrays

        for variable in fnPrototypes.paramlist:
            for dependency in dependencies[variable]:
                if not self.signature.getParam(dependency):
                    self.signature.append(dependency, fnPrototypes.getParam(dependency))

    def getFnParam(self, name):
        return self.signature.getParam(name)

    @property
    def num_params(self):
        return len(self.signature.paramlist)

    @property
    def estimated_size(self):
        total = getParamSequenceSize((self.getFnParam(paramName).winType for paramName in self.signature.paramlist), True)

        if total < 32:
            total = 32
        elif total > 1024:
            total = 1024

        return total



class FunctionSignature:
    def __repr__(self):
        return ", ".join(self.paramlist)

    def __init__(self):
        self.LUT       = {} # dictionary of FunctionParameter
        self.paramlist = [] # list of parameters to maintain their order in signature

    def append(self,variable,fnparam):
        self.LUT[variable] = fnparam
        self.paramlist.append(variable)

    def getParam(self,variable):
        return self.LUT.get(variable)

    def getLength(self):
        return len(self.paramlist)

class FunctionParameter:
    def __repr__(self):
        return self.name

    def __init__(self,winType,name,count,prop):
        self.winType  = winType   #ETW type as given in the manifest
        self.name     = name      #parameter name as given in the manifest
        self.prop     = prop      #any special property as determined by the manifest and developer
        #self.count               #indicates if the parameter is a pointer
        if  count == "win:null":
            self.count    = "win:null"
        elif count or winType == "win:GUID" or count == "win:count":
        #special case for GUIDS, consider them as structs
            self.count    = "win:count"
        else:
            self.count    = "win:null"


def getTopLevelElementsByTagName(node,tag):
    dataNodes = []
    for element in node.getElementsByTagName(tag):
        if element.parentNode == node:
            dataNodes.append(element)

    return dataNodes

ignoredXmlTemplateAttribes = frozenset(["map","outType"])
usedXmlTemplateAttribes    = frozenset(["name","inType","count", "length"])

def parseTemplateNodes(templateNodes):

    #return values
    allTemplates           = {}

    for templateNode in templateNodes:
        structCounts = {}
        arrays = {}
        templateName    = templateNode.getAttribute('tid')
        var_Dependecies = {}
        fnPrototypes    = FunctionSignature()
        dataNodes       = getTopLevelElementsByTagName(templateNode,'data')

        # Validate that no new attributes has been added to manifest
        for dataNode in dataNodes:
            nodeMap = dataNode.attributes
            for attrib in nodeMap.values():
                attrib_name = attrib.name
                if attrib_name not in ignoredXmlTemplateAttribes and attrib_name not in usedXmlTemplateAttribes:
                    raise ValueError('unknown attribute: '+ attrib_name + ' in template:'+ templateName)

        for dataNode in dataNodes:
            variable = dataNode.getAttribute('name')
            wintype = dataNode.getAttribute('inType')

            #count and length are the same
            wincount  = dataNode.getAttribute('count')
            winlength = dataNode.getAttribute('length');

            var_Props = None
            var_dependency = [variable]
            if  winlength:
                if wincount:
                    raise Exception("both count and length property found on: " + variable + "in template: " + templateName)
                wincount = winlength

            if (wincount.isdigit() and int(wincount) ==1):
                wincount = ''

            if  wincount:
                if (wincount.isdigit()):
                    var_Props = wincount
                elif  fnPrototypes.getParam(wincount):
                    var_Props = wincount
                    var_dependency.insert(0, wincount)
                    arrays[variable] = wincount

            #construct the function signature

            if  wintype == "win:GUID":
                var_Props = "sizeof(GUID)/sizeof(int)"

            var_Dependecies[variable] = var_dependency
            fnparam        = FunctionParameter(wintype,variable,wincount,var_Props)
            fnPrototypes.append(variable,fnparam)

        structNodes = getTopLevelElementsByTagName(templateNode,'struct')

        for structToBeMarshalled in structNodes:
            structName   = structToBeMarshalled.getAttribute('name')
            countVarName = structToBeMarshalled.getAttribute('count')

            assert(countVarName == "Count")
            assert(countVarName in fnPrototypes.paramlist)
            if not countVarName:
                raise ValueError("Struct '%s' in template '%s' does not have an attribute count." % (structName, templateName))

            names = [x.attributes['name'].value for x in structToBeMarshalled.getElementsByTagName("data")]
            types = [x.attributes['inType'].value for x in structToBeMarshalled.getElementsByTagName("data")]

            structCounts[structName] = countVarName
            var_Dependecies[structName] = [countVarName, structName]
            fnparam_pointer = FunctionParameter("win:Struct", structName, "win:count", countVarName)
            fnPrototypes.append(structName, fnparam_pointer)

        allTemplates[templateName] = Template(templateName, fnPrototypes, var_Dependecies, structCounts, arrays)

    return allTemplates

def generateClrallEvents(eventNodes,allTemplates):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventEnabled
        clrallEvents.append("inline BOOL EventEnabled")
        clrallEvents.append(eventName)
        clrallEvents.append("() {return ")
        clrallEvents.append("EventPipeEventEnabled" + eventName + "()")

        if os.name == 'posix':
            clrallEvents.append(" || (XplatEventLogger::IsEventLoggingEnabled() && EventXplatEnabled" + eventName + "());}\n\n")
        else:
            clrallEvents.append(" || EventXplatEnabled" + eventName + "();}\n\n")
        #generate FireEtw functions
        fnptype     = []
        fnbody      = []
        fnptype.append("inline ULONG FireEtw")
        fnptype.append(eventName)
        fnptype.append("(\n")

        line        = []
        fnptypeline = []

        if templateName:
            template = allTemplates[templateName]
            fnSig = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)
                wintypeName = fnparam.winType
                typewName   = palDataTypeMapping[wintypeName]
                winCount    = fnparam.count
                countw      = palDataTypeMapping[winCount]


                if params in template.structs:
                    fnptypeline.append("%sint %s_ElementSize,\n" % (lindent, params))

                fnptypeline.append(lindent)
                fnptypeline.append(typewName)
                fnptypeline.append(countw)
                fnptypeline.append(" ")
                fnptypeline.append(fnparam.name)
                fnptypeline.append(",\n")

            #fnsignature
            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)

                if params in template.structs:
                    line.append(fnparam.name + "_ElementSize")
                    line.append(", ")

                line.append(fnparam.name)
                line.append(",")

            #remove trailing commas
            if len(line) > 0:
                del line[-1]

        #add activity IDs
        fnptypeline.append(lindent)
        fnptypeline.append("LPCGUID ActivityId = nullptr,\n")
        fnptypeline.append(lindent)
        fnptypeline.append("LPCGUID RelatedActivityId = nullptr")

        fnptype.extend(fnptypeline)
        fnptype.append("\n)\n{\n")
        fnbody.append(lindent)

        fnbody.append("ULONG status = EventPipeWriteEvent" + eventName + "(" + ''.join(line))
        if len(line) > 0:
            fnbody.append(",")

        fnbody.append("ActivityId,RelatedActivityId);\n")

        fnbody.append(lindent)
        fnbody.append("status &= FireEtXplat" + eventName + "(" + ''.join(line) + ");\n")
        fnbody.append(lindent)
        fnbody.append("return status;\n")
        fnbody.append("}\n\n")

        clrallEvents.extend(fnptype)
        clrallEvents.extend(fnbody)

    return ''.join(clrallEvents)

def generateClrXplatEvents(eventNodes, allTemplates, extern):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventEnabled
        if extern: clrallEvents.append('extern "C" ')
        clrallEvents.append("BOOL EventXplatEnabled")
        clrallEvents.append(eventName)
        clrallEvents.append("();\n")

        #generate FireEtw functions
        fnptype     = []
        fnptypeline = []
        if extern: fnptype.append('extern "C" ')
        fnptype.append("ULONG FireEtXplat")
        fnptype.append(eventName)
        fnptype.append("(\n")

        if templateName:
            template = allTemplates[templateName]
            fnSig = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)
                wintypeName = fnparam.winType
                typewName   = palDataTypeMapping[wintypeName]
                winCount    = fnparam.count
                countw      = palDataTypeMapping[winCount]


                if params in template.structs:
                    fnptypeline.append("%sint %s_ElementSize,\n" % (lindent, params))

                fnptypeline.append(lindent)
                fnptypeline.append(typewName)
                fnptypeline.append(countw)
                fnptypeline.append(" ")
                fnptypeline.append(fnparam.name)
                fnptypeline.append(",\n")

            #remove trailing commas
            if len(fnptypeline) > 0:
                del fnptypeline[-1]

        fnptype.extend(fnptypeline)
        fnptype.append("\n);\n")
        clrallEvents.extend(fnptype)

    return ''.join(clrallEvents)

def generateClrEventPipeWriteEvents(eventNodes, allTemplates, extern):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventPipeEventEnabled and EventPipeWriteEvent functions
        eventenabled = []
        writeevent   = []
        fnptypeline  = []

        if extern:eventenabled.append('extern "C" ')
        eventenabled.append("BOOL EventPipeEventEnabled")
        eventenabled.append(eventName)
        eventenabled.append("();\n")

        if extern: writeevent.append('extern "C" ')
        writeevent.append("ULONG EventPipeWriteEvent")
        writeevent.append(eventName)
        writeevent.append("(\n")

        if templateName:
            template = allTemplates[templateName]
            fnSig    = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)
                wintypeName = fnparam.winType
                typewName   = palDataTypeMapping[wintypeName]
                winCount    = fnparam.count
                countw      = palDataTypeMapping[winCount]

                if params in template.structs:
                    fnptypeline.append("%sint %s_ElementSize,\n" % (lindent, params))

                fnptypeline.append(lindent)
                fnptypeline.append(typewName)
                fnptypeline.append(countw)
                fnptypeline.append(" ")
                fnptypeline.append(fnparam.name)
                fnptypeline.append(",\n")

        fnptypeline.append(lindent)
        fnptypeline.append("LPCGUID ActivityId = nullptr,\n")
        fnptypeline.append(lindent)
        fnptypeline.append("LPCGUID RelatedActivityId = nullptr")

        writeevent.extend(fnptypeline)
        writeevent.append("\n);\n")
        clrallEvents.extend(eventenabled)
        clrallEvents.extend(writeevent)

    return ''.join(clrallEvents)

#generates the dummy header file which is used by the VM as entry point to the logging Functions
def generateclrEtwDummy(eventNodes,allTemplates):
    clretmEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        fnptype     = []
        #generate FireEtw functions
        fnptype.append("#define FireEtw")
        fnptype.append(eventName)
        fnptype.append("(");
        line        = []
        if templateName:
            template = allTemplates[templateName]
            fnSig = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)

                if params in template.structs:
                    line.append(fnparam.name + "_ElementSize")
                    line.append(", ")

                line.append(fnparam.name)
                line.append(", ")

            #remove trailing commas
            if len(line) > 0:
                del line[-1]

        fnptype.extend(line)
        fnptype.append(") 0\n")
        clretmEvents.extend(fnptype)

    return ''.join(clretmEvents)

def generateEtmDummyHeader(sClrEtwAllMan,clretwdummy):

    if not clretwdummy:
        return

    tree           = DOM.parse(sClrEtwAllMan)

    incDir = os.path.dirname(os.path.realpath(clretwdummy))
    if not os.path.exists(incDir):
        os.makedirs(incDir)

    with open_for_update(clretwdummy) as Clretwdummy:
        Clretwdummy.write(stdprolog + "\n")

        for providerNode in tree.getElementsByTagName('provider'):
            templateNodes = providerNode.getElementsByTagName('template')
            allTemplates  = parseTemplateNodes(templateNodes)
            eventNodes = providerNode.getElementsByTagName('event')
            #pal: create etmdummy.h
            Clretwdummy.write(generateclrEtwDummy(eventNodes, allTemplates) + "\n")

def convertToLevelId(level):
    if level == "win:LogAlways":
       return 0
    if level == "win:Critical":
       return 1
    if level == "win:Error":
       return 2
    if level == "win:Warning":
       return 3
    if level == "win:Informational":
       return 4
    if level == "win:Verbose":
       return 5
    raise Exception("unknown level " + level)

def getKeywordsMaskCombined(keywords, keywordsToMask):
    mask = 0
    for keyword in keywords.split(" "):
       if keyword == "":
          continue
       mask |= keywordsToMask[keyword]

    return mask

def generatePlatformIndependentFiles(sClrEtwAllMan, incDir, etmDummyFile, extern, write_xplatheader):

    generateEtmDummyHeader(sClrEtwAllMan,etmDummyFile)
    tree           = DOM.parse(sClrEtwAllMan)

    if not incDir:
        return

    if not os.path.exists(incDir):
        os.makedirs(incDir)

    eventpipe_trace_context_typedef = """
#if !defined(EVENTPIPE_TRACE_CONTEXT_DEF)
#define EVENTPIPE_TRACE_CONTEXT_DEF
typedef struct _EVENTPIPE_TRACE_CONTEXT
{
    WCHAR const * Name;
    UCHAR Level;
    bool IsEnabled;
    ULONGLONG EnabledKeywordsBitmask;
} EVENTPIPE_TRACE_CONTEXT, *PEVENTPIPE_TRACE_CONTEXT;
#endif // EVENTPIPE_TRACE_CONTEXT_DEF
"""

    lttng_trace_context_typedef = """
#if !defined(LTTNG_TRACE_CONTEXT_DEF)
#define LTTNG_TRACE_CONTEXT_DEF
typedef struct _LTTNG_TRACE_CONTEXT
{
    WCHAR const * Name;
    UCHAR Level;
    bool IsEnabled;
    ULONGLONG EnabledKeywordsBitmask;
} LTTNG_TRACE_CONTEXT, *PLTTNG_TRACE_CONTEXT;
#endif // LTTNG_TRACE_CONTEXT_DEF
"""

    dotnet_trace_context_typedef_windows = """
#if !defined(DOTNET_TRACE_CONTEXT_DEF)
#define DOTNET_TRACE_CONTEXT_DEF
typedef struct _DOTNET_TRACE_CONTEXT
{
    PMCGEN_TRACE_CONTEXT EtwProvider;
    EVENTPIPE_TRACE_CONTEXT EventPipeProvider;
} DOTNET_TRACE_CONTEXT, *PDOTNET_TRACE_CONTEXT;
#endif // DOTNET_TRACE_CONTEXT_DEF
"""

    dotnet_trace_context_typedef_unix = """
#if !defined(DOTNET_TRACE_CONTEXT_DEF)
#define DOTNET_TRACE_CONTEXT_DEF
typedef struct _DOTNET_TRACE_CONTEXT
{
    EVENTPIPE_TRACE_CONTEXT EventPipeProvider;
    PLTTNG_TRACE_CONTEXT LttngProvider;
} DOTNET_TRACE_CONTEXT, *PDOTNET_TRACE_CONTEXT;
#endif // DOTNET_TRACE_CONTEXT_DEF
"""

    # Write the main header for FireETW* functions
    clrallevents = os.path.join(incDir, "clretwallmain.h")
    is_windows = os.name == 'nt'
    with open_for_update(clrallevents) as Clrallevents:
        Clrallevents.write(stdprolog)
        Clrallevents.write("""
#include "clrxplatevents.h"
#include "clreventpipewriteevents.h"

""")

        # define DOTNET_TRACE_CONTEXT depending on the platform
        if is_windows:
            Clrallevents.write(eventpipe_trace_context_typedef)  # define EVENTPIPE_TRACE_CONTEXT
            Clrallevents.write(dotnet_trace_context_typedef_windows)

        for providerNode in tree.getElementsByTagName('provider'):
            templateNodes = providerNode.getElementsByTagName('template')
            allTemplates  = parseTemplateNodes(templateNodes)
            eventNodes = providerNode.getElementsByTagName('event')

            #vm header:
            Clrallevents.write(generateClrallEvents(eventNodes, allTemplates) + "\n")

            providerName = providerNode.getAttribute('name')
            providerSymbol = providerNode.getAttribute('symbol')

            if is_windows:
                eventpipeProviderCtxName = providerSymbol + "_EVENTPIPE_Context"
                Clrallevents.write('constexpr EVENTPIPE_TRACE_CONTEXT ' + eventpipeProviderCtxName + ' = { W("' + providerName + '"), 0, false, 0 };\n')

    if write_xplatheader:
        clrproviders = os.path.join(incDir, "clrproviders.h")
        with open_for_update(clrproviders) as Clrproviders:
            Clrproviders.write("""
typedef struct _EVENT_DESCRIPTOR
{
    int const Level;
    ULONGLONG const Keyword;
} EVENT_DESCRIPTOR;
""")

            if not is_windows:
                Clrproviders.write(eventpipe_trace_context_typedef)  # define EVENTPIPE_TRACE_CONTEXT
                Clrproviders.write(lttng_trace_context_typedef)  # define LTTNG_TRACE_CONTEXT
                Clrproviders.write(dotnet_trace_context_typedef_unix)

            allProviders = []
            nbProviders = 0
            for providerNode in tree.getElementsByTagName('provider'):
                keywords = []
                keywordsToMask = {}
                providerName = str(providerNode.getAttribute('name'))
                providerSymbol = str(providerNode.getAttribute('symbol'))
                nbProviders += 1
                nbKeywords = 0
                if not is_windows:
                    eventpipeProviderCtxName = providerSymbol + "_EVENTPIPE_Context"
                    Clrproviders.write('__attribute__((weak)) EVENTPIPE_TRACE_CONTEXT ' + eventpipeProviderCtxName + ' = { W("' + providerName + '"), 0, false, 0 };\n')
                    lttngProviderCtxName = providerSymbol + "_LTTNG_Context"
                    Clrproviders.write('__attribute__((weak)) LTTNG_TRACE_CONTEXT ' + lttngProviderCtxName + ' = { W("' + providerName + '"), 0, false, 0 };\n')

                Clrproviders.write("// Keywords\n");
                for keywordNode in providerNode.getElementsByTagName('keyword'):
                    keywordName = keywordNode.getAttribute('name')
                    keywordMask = keywordNode.getAttribute('mask')
                    keywordSymbol = keywordNode.getAttribute('symbol')
                    Clrproviders.write("#define " + keywordSymbol + " " + keywordMask + "\n")

                    keywords.append("{ \"" + keywordName + "\", " + keywordMask + " }")
                    keywordsToMask[keywordName] = int(keywordMask, 16)
                    nbKeywords += 1

                for eventNode in providerNode.getElementsByTagName('event'):
                    levelName = eventNode.getAttribute('level')
                    symbolName = eventNode.getAttribute('symbol')
                    keywords = eventNode.getAttribute('keywords')
                    level = convertToLevelId(levelName)
                    Clrproviders.write("constexpr EVENT_DESCRIPTOR " + symbolName + " = { " + str(level) + ", " + hex(getKeywordsMaskCombined(keywords, keywordsToMask)) + " };\n")

                allProviders.append("&" + providerSymbol + "_LTTNG_Context")

            # define and initialize runtime providers' DOTNET_TRACE_CONTEXT depending on the platform
            if not is_windows:
                Clrproviders.write('#define NB_PROVIDERS ' + str(nbProviders) + '\n')
                Clrproviders.write('constexpr LTTNG_TRACE_CONTEXT * ALL_LTTNG_PROVIDERS_CONTEXT[NB_PROVIDERS] = { ')
                Clrproviders.write(', '.join(allProviders))
                Clrproviders.write(' };\n')


    clreventpipewriteevents = os.path.join(incDir, "clreventpipewriteevents.h")
    with open_for_update(clreventpipewriteevents) as Clreventpipewriteevents:
        Clreventpipewriteevents.write(stdprolog + "\n")

        for providerNode in tree.getElementsByTagName('provider'):
            templateNodes = providerNode.getElementsByTagName('template')
            allTemplates  = parseTemplateNodes(templateNodes)
            eventNodes = providerNode.getElementsByTagName('event')

            #eventpipe: create clreventpipewriteevents.h
            Clreventpipewriteevents.write(generateClrEventPipeWriteEvents(eventNodes, allTemplates, extern) + "\n")

    # Write secondary headers for FireEtXplat* and EventPipe* functions
    if write_xplatheader:
        clrxplatevents = os.path.join(incDir, "clrxplatevents.h")
        with open_for_update(clrxplatevents) as Clrxplatevents:
            Clrxplatevents.write(stdprolog + "\n")

            for providerNode in tree.getElementsByTagName('provider'):
                templateNodes = providerNode.getElementsByTagName('template')
                allTemplates  = parseTemplateNodes(templateNodes)
                eventNodes = providerNode.getElementsByTagName('event')

                #pal: create clrallevents.h
                Clrxplatevents.write(generateClrXplatEvents(eventNodes, allTemplates, extern) + "\n")

import argparse
import sys

def main(argv):

    #parse the command line
    parser = argparse.ArgumentParser(description="Generates the Code required to instrument LTTtng logging mechanism")

    required = parser.add_argument_group('required arguments')
    required.add_argument('--man',  type=str, required=True,
                                    help='full path to manifest containig the description of events')
    required.add_argument('--inc',  type=str, default=None,
                                    help='full path to directory where the header files will be generated')
    required.add_argument('--dummy',  type=str,default=None,
                                    help='full path to file that will have dummy definitions of FireEtw functions')
    required.add_argument('--nonextern', action='store_true',
                                    help='if specified, will not generated extern function stub headers' )
    required.add_argument('--noxplatheader', action='store_true',
                                    help='if specified, will not write a generated cross-platform header' )
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print('Unknown argument(s): ', ', '.join(unknown))
        return 1

    sClrEtwAllMan     = args.man
    incdir            = args.inc
    etmDummyFile      = args.dummy
    extern            = not args.nonextern
    write_xplatheader = not args.noxplatheader

    generatePlatformIndependentFiles(sClrEtwAllMan, incdir, etmDummyFile, extern, write_xplatheader)

if __name__ == '__main__':
    return_code = main(sys.argv[1:])
    sys.exit(return_code)