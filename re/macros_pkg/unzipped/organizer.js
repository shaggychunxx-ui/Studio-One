
MacroOrganizer.prototype = new CCL.JS.Component ();
function MacroOrganizer ()
{	
	this.initialize = function (context)
	{	
		CCL.JS.Component.prototype.initialize.call (this, context);
		
		// get macro manager from service, must not fail!
		this.macroManager = getSharedMacroManager ();

		this.paramList.addParam ("new");
		this.paramList.addParam ("edit");
		this.paramList.addParam ("delete");
		this.paramList.addParam ("refresh");
		this.paramList.addParam ("showFolder");
		this.paramList.addString ("searchString");
		this.paramList.addParam ("clear")
		this.paramList.addParam ("editShortcut")
		
		// create model for file list
		this.fileList = ccl_new ("Host:ListViewModel");
		this.fileList.columns.addColumn (200, JSTRANSLATE ("Name"), CCL.JS.Columns.kTitleID, 50, CCL.JS.Columns.kSizable|CCL.JS.Columns.kCanFit|CCL.JS.Columns.kSortable);
		this.fileList.columns.addColumn (150, JSTRANSLATE ("Group"), "group", 50, CCL.JS.Columns.kSizable|CCL.JS.Columns.kCanFit|CCL.JS.Columns.kSortable);
		this.fileList.columns.addColumn (200, JSTRANSLATE ("Description"), "description", 100, CCL.JS.Columns.kSizable|CCL.JS.Columns.kCanFit|CCL.JS.Columns.kSortable);
		this.fileList.columns.addColumn (150, JSTRANSLATE ("Shortcut"), "shortcut", 100, CCL.JS.Columns.kSizable|CCL.JS.Columns.kCanFit|CCL.JS.Columns.kSortable); // column index has special open handling
		this.fileList.addTitleSorter ("Name");
		this.fileList.addDetailSorter ("group", "group");
		this.fileList.addDetailSorter ("description", "description");
		this.fileList.addDetailSorter ("shortcut", "shortcut");
		this.updateFileList ();

		// add dependencies
		Host.Signals.advise (this.fileList, this);
		Host.Signals.advise (kMacrosSignal, this);

		return Host.Results.kResultOk;
	}
	
	this.terminate = function ()
	{
		// remove dependencies
		Host.Signals.unadvise (this.fileList, this);
		Host.Signals.unadvise (kMacrosSignal, this);
	
		return CCL.JS.Component.prototype.terminate.call (this);
	}
	
	this.updateFileList = function ()
	{
		this.fileList.removeAll ();
		
		// create list of macros sorted by group/title
		var sortedMacros = new Array;
		for(let i in this.macroManager.macros)
			sortedMacros.push (this.macroManager.macros[i]);

		// sort alphabetically by 1.) group, 2.) title
		sortedMacros.sort (function (a, b) {
			let result = a.group.localeCompare (b.group);
			return result ? result : a.title.localeCompare (b.title);
		});

		for(let i in sortedMacros)
		{
			let macro = sortedMacros[i];

			let searchString = this.paramList.lookup ("searchString").string;
			if(searchString.length != 0)
				if(!macro.title.toLowerCase ().includes (searchString.toLowerCase ()) &&
				   !macro.group.toLowerCase ().includes (searchString.toLowerCase ()))
					continue;
	
			let item = this.fileList.newItem (macro.title);
			item.details.group = macro.group;
			item.details.description = macro.description;
			item.details.data = macro; // keep reference to macro object
			
			let commandName = this.macroManager.makeCommandName (macro);
			let command = Host.GUI.Commands.findCommand (kMacrosCategory, commandName);
			if(command)
			{
				let key = Host.GUI.Commands.lookupKeyEvent (command);
				item.details.shortcut = key ? key.toString (true) : "";
			}
			
			this.fileList.addItem (item);
		}
		
		this.fileList.changed ();
	}
	
	this.runDialog = function ()
	{
		return Host.GUI.runDialog (this.getTheme (), "MacroOrganizer", this);
	}

	this.paramChanged = function (param)
	{
		switch(param.name)
		{
		case "new"			: this.onNewMacro (); break;
		case "edit"			: this.onEditMacro (this.fileList.getFocusItem ()); break;
		case "delete"		: this.onDeleteMacros (); break;
		case "refresh"		: this.onRefresh (); break;
		case "showFolder"	: this.onShowFolder (); break;
		case "searchString"	: this.updateFileList (); break;
		case "clear"		: this.clearSearch (); break;
		case "editShortcut"	: this.onEditShortcut (this.fileList.getFocusItem ()); break;
		}	
	}
	
	this.notify = function (subject, msg)
	{
		if(subject == kMacrosSignal)
		{
			if(msg.id == kMacrosRescanned)
				this.updateFileList ();
		}
		else if(msg.id == CCL.JS.kItemOpened)
		{
			if(subject == this.fileList)
			{
				let macro = msg.getArg (0);
				let column = msg.getArg (1);
				if(column == 3) // shortcut column
					this.onEditShortcut (macro)
				else
					this.onEditMacro (macro);
			}
		}
		else if(msg.id == CCL.JS.kItemFocused)
		{
			if(subject == this.fileList)
			{
				let item = this.fileList.getFocusItem ();
				let macro = item ? item.details.data : null;
				let readOnly = macro ? macro.readOnly : false;
			
				this.paramList.lookup ("edit").enabled = !readOnly;
				this.paramList.lookup ("delete").enabled = !readOnly;
			}
		}
		else
			CCL.JS.Component.prototype.notify.call (this, subject, msg);
	}
	
	this.onRefresh = function ()
	{
		this.macroManager.rescanAll ();
	}
	
	this.onShowFolder = function ()
	{
		Host.GUI.showInBrowser (this.macroManager.getMacrosFolder ());
	}
	
	this.onNewMacro = function ()
	{
		var editor = new MacroEditor;
		editor.initialize ();

		let macroID = null;

		if(editor.runDialog () == Host.GUI.Constants.kOkay)
		{
			let macro = editor.getMacro ();
			
			if(macro.title.length == 0)
				macro.title = JSTRANSLATE ("User Macro");
			
			let fileName = this.macroManager.makeMacroFileName (macro.title);

			let path = this.macroManager.getMacrosFolder ();
			path.descend (fileName);
			path.makeUnique ();

			macro.saveToFile (path);
			macroID = this.macroManager.makeMacroID (path);

			this.onRefresh ();
		}
		
		editor.terminate ();
		return macroID;
	}

	this.onEditMacro = function (item)
	{
		if(item == null)
			return;
			
		var macro = item.details.data;
		this.editMacro (macro);
	}

	this.editMacro = function (macro)
	{
		if(macro.readOnly)
			return false;

		var editor = new MacroEditor;
		editor.initialize ();
		
		editor.setMacro (macro);
					
		if(editor.runDialog () == Host.GUI.Constants.kOkay)
		{
			let newMacro = editor.getMacro ();
			newMacro.originalPath = macro.originalPath;
						
			newMacro.save ();

			let renamed = false;
			if(newMacro.title != macro.title)
			{
				let messageText = newMacro.title + "\n\n" + JSTRANSLATE ("Do you want to rename the macro file as well?");
				if(Host.GUI.ask (messageText) == 0) // "Yes"
					renamed = this.macroManager.renameMacroFile (newMacro, newMacro.title);
			}

			if(!renamed) // manager already rescanned on rename
				this.onRefresh ();
		}
		
		editor.terminate ();
	}
	
	this.onDeleteMacros = function ()
	{
		var candidates = this.fileList.getSelectedItems ();
		if(candidates.length == 0)
			return;
			
		if(Host.GUI.ask (JSTRANSLATE ("Do you want to delete the selected macros?")) != Host.GUI.Constants.kYes)
			return;
			
		var iter = candidates.newIterator ();
		while(!iter.done ())
		{
			var item = iter.next ();
			var macro = item.details.data;
			Host.IO.File (macro.originalPath).remove ();
		}
		
		this.onRefresh ();
	}
	
	this.onEditShortcut = function (item)
	{
		if(item == null)
			return;
			
		let macro = item.details.data;
		let commandName = getSharedMacroManager ().makeCommandName (macro);
		
		let args = Host.Attributes (["InitialCategory", kMacrosCategory, "InitialCommand", commandName]);
		Host.GUI.Commands.interpretCommand ("Application", "Keyboard Shortcuts", false, args);
		
		let index = this.fileList.itemView.getFocusItem ();
		this.updateFileList ();
		this.fileList.itemView.setFocusItem (index);
	}

	this.clearSearch = function ()
	{
		this.paramList.lookup ("searchString").string = "";
		this.updateFileList ();
	}

	this.focusSearchField = function ()
	{
		this.clearSearch ();
		Host.Signals.signal (this.paramList.lookup ("searchString"), CCL.JS.kRequestFocus);
	}
}
