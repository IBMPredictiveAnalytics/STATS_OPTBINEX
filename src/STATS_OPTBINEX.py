#/***********************************************************************
# * Licensed Materials - Property of IBM 
# *
# * IBM SPSS Products: Statistics Common
# *
# * (C) Copyright IBM Corp. 1989, 2014
# *
# * US Government Users Restricted Rights - Use, duplication or disclosure
# * restricted by GSA ADP Schedule Contract with IBM Corp. 
# ************************************************************************/


"""STATS OUTPUT ATTRS extension command"""

__author__ =  'JKP'
__version__=  '1.0.0'

# history
# 25-oct-2014 original version

import spss, spssaux, SpssClient, tempfile, random, os
from extension import Template, Syntax, processcmd


def dooptbinex(target, binvars, suffix=["_bin"], minsize=10,
    alpha=.05, overwrite=False, syntaxoutfile=None, contintervals=10,
    treetable=True, recodetable=True, execute=True):
    """Execute STATS OPTBINEX command"""
    
        # debugging
    # makes debug apply only to the current thread
    #try:
        #import wingdbstub
        #if wingdbstub.debugger != None:
            #import time
            #wingdbstub.debugger.StopDebug()
            #time.sleep(2)
            #wingdbstub.debugger.StartDebug()
        #import thread
        #wingdbstub.debugger.SetDebugThreads({thread.get_ident(): 1}, default_policy=0)
        ## for V19 use
        #SpssClient._heartBeat(False)
    #except:
        #pass
    
    # Check that TREES procedure is licensed if possible
    treesavailable = True
    try:    # no client in external mode
        SpssClient.StartClient()
        treesavailable = SpssClient.IsOptionAvailable(SpssClient.LicenseOption.TREEVIEW)
    except:
        pass
    finally:
        SpssClient.StopClient()
    if not treesavailable:
        raise ValueError(_("""Error: This command requires the Decision Trees option, which is not licensed."""))

    if syntaxoutfile is None and not execute:
        raise ValueError(_("""No syntax output was specified, and execution was not requested.
There is nothing to do."""))
    suffix = "".join(suffix)   #tokenlist may come through with mult elements
    outnames = [v + suffix for v in binvars]
    toolong = [v for v in outnames if len(v) > 64]  # wrong metric for Unicode
    if toolong:
        raise ValueError(_("""The following new names exceed 64 bytes.
Please choose a shorter suffix or rename the input variables:\n%s""") % " ".join(toolong))
    vardict = spssaux.VariableDict()
    if not overwrite:
        existingnames = set([v.lower() for v in vardict.variables])
        onames = existingnames.intersection(set([v.lower() for v in outnames]))
        if onames:
            raise ValueError(_("""Error: The following variables would be overwritten:\n%s""")\
                % " ".join(onames))
      
    xmlws = "x" + str(random.uniform(.1,1))
    visible = (treetable and "yes") or "no"
    tempdir = tempfile.gettempdir()
    rulesfilespec = os.path.join(tempdir, "F" + str(random.uniform(.1,1)))

    treetemplate = """TREE %(target)s BY %(indvar)s    
/TREE DISPLAY=NONE /PRINT TREETABLE /GAIN SUMMARYTABLE=NO
/RULES OUTFILE="%(rulesfilespec)s"
/GROWTHLIMIT MAXDEPTH=1 MINPARENTSIZE=10 MINCHILDSIZE=%(minsize)s
/CHAID ALPHASPLIT=%(alpha)s INTERVALS=%(contintervals)s.
"""
    if syntaxoutfile is None:
        insertfile = os.path.join(tempdir, "F" + str(random.uniform(.1,1)))
    else:
        insertfile = syntaxoutfile
    insertfilef = open(insertfile, "wb")
    
    # run TREES for each independent variable and accumulate resulting tranformations
    
    oattrs = spssaux.getShow("OATTRS")
    empty = True
    failedvars = []
    outvars = []
    outlabels = []
    try:
        for indvar in binvars:
            # set OMS to use language-invariant text
            spss.Submit("""set oattrs=eng.
    oms select tables /if subtypes='TreeTable'
    /destination format=oxml xmlworkspace="%(xmlws)s" viewer=%(visible)s
    /tag = "%(xmlws)s".
    """ % locals())
            spss.Submit(treetemplate % locals())
            spss.Submit("""omsend tag="%(xmlws)s".""" % locals())
            labels = spss.EvaluateXPath(xmlws, "/", 
                """//pivotTable//group[@text_eng="Primary Independent Variable"]/category[@text_eng="Split Values"]/cell/@text""")
            if not labels:
                failedvars.append(indvar)
                continue
            empty = False
            outputname = indvar + suffix
            if recodetable:
                outvars.append(outputname)
                outlabels.append(labels)
            definitions = getrules(rulesfilespec, outputname, labels, 
                vardict[indvar].VariableLabel)  # also removes temporary file
            insertfilef.writelines([line + "\n" for line in definitions])
    finally:    
        insertfilef.close()
        spss.Submit("SET OATTRS=%s" % oattrs)  # restore setting
        spss.DeleteXPathHandle(xmlws)            
    if execute and not empty:
        spss.Submit("""INSERT FILE="%s".""" % insertfile)
    if syntaxoutfile is None:
        os.remove(insertfile)
        
    if failedvars or recodetable:
        from spss import CellText
        StartProcedure(_("Extended Optimal Binning"), "STATSOPTBINEX")
        if failedvars:
            wtable = spss.BasePivotTable("Warnings ", "Warnings")
            wtable.Append(spss.Dimension.Place.row, "rowdim", hideLabels=True)
            rowLabel = CellText.String("1")
            wtable[(rowLabel,)] = \
            spss.CellText.String(_("""These variables could not be binned.  New variables were not created for them.\n%s""") % " ".join(failedvars))

        if recodetable and not empty:
            table = spss.BasePivotTable(_("Variable Binning"), "OPTBIN")
            table.Append(spss.Dimension.Place.row, _("Variable"))
            table.Append(spss.Dimension.Place.row, _("Value"))
            table.Append(spss.Dimension.Place.column, _("Definition"), 
                hideName=True)
            reccoldef = CellText.String("Definition")
            for i in range(len(outvars)):
                var = CellText.String(outvars[i])
                for j, val in enumerate(outlabels[i]):
                    rec = CellText.String(j)
                    recval = CellText.String(val)
                    table[(var, rec, reccoldef)] = recval
        spss.EndProcedure()
        
def getrules(rulesfilespec, varname, labels, varlabel):
    """Return a list of rules written by TREES CHAID
    
    rulesfilespec is the file containing the rules
    It should contain rules like this...
/* Node 2 */.
DO IF (SYSMIS(prevexp) OR (VALUE(prevexp) GT 5  AND  VALUE(prevexp) LE 261)).
COMPUTE nod_001 = 2.
COMPUTE pre_001 = 36410.7804232804.
END IF.
EXECUTE.

    varname is the name for the output variable
    labels is a list of labels for the values"""
    
    # rule file is written in the current Statistics encoding mode
    # but does not have a BOM
    # Try to passively ignore this.
    
    f = open(rulesfilespec, "r")
    lines = []   # accumulates generated syntax
    continuation = False   # indicates whether on a continuation line in the rules file
    code = 0   # holds the new values
    for line in f.readlines():
        line = line[:-1]  # strip trailing newline
        if line.startswith("DO IF") or continuation:
            lines.append(line)
            if not line.endswith("."):
                continuation = True
            else:
                continuation = False
        if line.startswith("END IF"):
            lines.append("""COMPUTE %(varname)s = %(code)s.""" % locals())
            code += 1
            lines.append(line)   # the END IF, which
    f.close()
    labelspec = "\n".join([str(i) + " " + spssaux._smartquote(val) for i, val in enumerate(labels)])
    if varlabel:
        varlabel = spssaux._smartquote(varlabel)
        lines.append("""VARIABLE LABEL %(varname)s %(varlabel)s.""" % locals())
    lines.append("""VALUE LABELS %(varname)s""" % locals())
    lines.append(labelspec)
    lines.append(".")
    return lines
        
def StartProcedure(procname, omsid):
    """Start a procedure
    
    procname is the name that will appear in the Viewer outline.  It may be translated
    omsid is the OMS procedure identifier and should not be translated.
    
    Statistics versions prior to 19 support only a single term used for both purposes.
    For those versions, the omsid will be use for the procedure name.
    
    While the spss.StartProcedure function accepts the one argument, this function
    requires both."""
    
    try:
        spss.StartProcedure(procname, omsid)
    except TypeError:  #older version
        spss.StartProcedure(omsid)
        
def Run(args):
    """Execute the STATS OPTBINEX extension command"""

    args = args[args.keys()[0]]

    oobj = Syntax([
        Template("TARGET", subc="",  ktype="existingvarlist", var="target", islist=False),
        Template("BINVARS", subc="",  ktype="existingvarlist", var="binvars", islist=True),
        Template("SUFFIX", subc="", ktype="literal", var="suffix", islist=True),
        Template("OVERWRITE", subc="", ktype="bool", var="overwrite"),
        
        Template("MINSIZE", subc="OPTIONS", ktype="int", var="minsize",
            vallist=(1,)),
        Template("ALPHA", subc="OPTIONS", ktype="float", var="alpha",
            vallist=(.00001, .50)),
        Template("CONTINTERVALS", subc="OPTIONS", ktype="int", var="contintervals",
            vallist=[2, 64]),
        Template("SYNTAXOUTFILE", subc="OPTIONS", ktype="literal", var="syntaxoutfile"),
        Template("EXECUTE", subc="OPTIONS", ktype="bool", var="execute"),
        Template("TREETABLE", subc="OPTIONS", ktype="bool", var="treetable"),
        Template("RECODETABLE", subc="OPTIONS", ktype="bool", var="recodetable"),
        
        Template("HELP", subc="", ktype="bool")])

    
    #enable localization
    global _
    try:
        _("---")
    except:
        def _(msg):
            return msg
    # A HELP subcommand overrides all else
    if args.has_key("HELP"):
        #print helptext
        helper()
    else:
        processcmd(oobj, args, dooptbinex, vardict=spssaux.VariableDict())

def helper():
    """open html help in default browser window
    
    The location is computed from the current module name"""
    
    import webbrowser, os.path
    
    path = os.path.splitext(__file__)[0]
    helpspec = "file://" + path + os.path.sep + \
         "markdown.html"
    
    # webbrowser.open seems not to work well
    browser = webbrowser.get()
    if not browser.open_new(helpspec):
        print("Help file not found:" + helpspec)
try:    #override
    from extension import helper
except:
    pass