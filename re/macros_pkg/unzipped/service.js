include_file("resource://{main}/sdk/cclapp.js");
include_file ("elements.js");
include_file ("manager.js");

function MacroManagerService ()
{
	this.interfaces = [Host.Interfaces.IComponent, Host.Interfaces.IObserver];
	
	/** Called by panel and gadget to get the shared macro manager instance */
	this.getMacroManager = function ()
	{
		return theMacroManager;
	}		

	// IComponent
	this.initialize = function ()
	{	
		// scan for macros
		theMacroManager.startup ();
		
		// register file handler
		Host.FileTypes.registerHandler (theMacroFileType, theMacroManager.getMacrosFolder (), this);
		Host.FileTypes.registerHandler (theMacroPageFileType, 0, this);

		return Host.Results.kResultOk;
	}
	
	this.terminate = function ()
	{
		// unregister file handler
		Host.FileTypes.unregisterHandler (theMacroFileType);
		Host.FileTypes.unregisterHandler (theMacroPageFileType);
		
		return Host.Results.kResultOk;
	}	
	
	// IObserver
	this.notify = function (subject, msg)
	{
		if(msg.id == CCL.JS.kOpenFile)
		{
			let url = msg.getArg (0);
			if(url && url.extension == theMacroPageFileType.extension)
			{
				// macro page file: trigger import as new page
				Host.Signals.signal (kMacrosSignal, kImportMacroPage, url)
			}
			else
			{
				// macro file: open organizer + rescan
				Host.GUI.Commands.interpretCommand ("Gadgets", "Macro Organizer", false, Host.Attributes (new Array ("State", "1")));
				theMacroManager.rescanAll ();
			}
		}
	}
}

//////////////////////////////////////////////////////////////////////////////////////////////////
// Class factory entry point
//////////////////////////////////////////////////////////////////////////////////////////////////

function createInstance (args)
{
	__init (args); // init package identifier

	return new MacroManagerService;
}
