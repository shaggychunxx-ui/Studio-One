
//************************************************************************************************
// MacroManager
//************************************************************************************************

MacroManager = function ()
{
	this.macros = [];
	this.extractedPageFiles = [];
	
	this.getMacrosFolder = function ()
	{
		return Host.Url ("local://$USERCONTENT/Macros", true);
	}

	this.getMacrosMemoryFolder = function (locationId)
	{
		// avoid subfolders
		let hostName = "Macros-" + locationId;
		return Host.Url ("memory://" + hostName, true);
	}
	
	this.getFactoryMacrosFolder = function ()
	{
		return CCL.JS.ResourceUrl ("library", true);
	}

	this.getExtensionHandler = function (index)
	{
		return Host.Objects.getObjectByUrl ("MacroExtensionHandler");
	}

	this.getAdditionalReadFolders = function ()
	{
		// MacroExtensionHandler provides macro locations from extensions
		let handler = this.getExtensionHandler ();
		if(handler)
			return handler.macroLocations;

		return null;
	}

	this.collectPageFilesToImport = function ()
	{
		let paths = [];

		let readFolders = this.getAdditionalReadFolders ();
		if(readFolders)
			for(let f in readFolders)
			{
				let folderItem = readFolders[f];
				let iter = Host.IO.findFiles (folderItem.path, "*." + theMacroPageFileType.extension);
				while(!iter.done ())
				{
					let pagePath = iter.next ();
					let id = folderItem.id + "." + pagePath.getName (false);
					paths.push ({ id: id , path: pagePath });
				}
			}
		return paths;
	}

	this.getFolderID = function (macroPath)
	{
		if(!this.getMacrosFolder ().contains (macroPath))
		{
			let handler = this.getExtensionHandler ();
			if(handler)
				return handler.getFolderID (macroPath);
		}
		return "";
	}

	this.getRevisionFile = function (folder)
	{
		let revisionFile = Host.Url (folder);
		revisionFile.descend ("macrosrevision.txt");
		return revisionFile;
	}

	this.getMacrosRevision = function (folder)
	{
		let revision = -1; // doesn't exist

		let revisionFile = this.getRevisionFile (folder);
		if(Host.IO.File (revisionFile).exists ())
		{
			let textFile = Host.IO.openTextFile (revisionFile);
			if(textFile)
			{
				let text = textFile.readLine ();
				revision = parseInt (text);
				textFile.close ();
			}
		}
		return revision;
	}

	this.startup = function ()
	{
		// copy factory macros to user folder if factory revision is higher (e.g. upon first startup)
		let userPath = this.getMacrosFolder ();

		let userRevision = this.getMacrosRevision (userPath);
		let factoryRevision = this.getMacrosRevision (this.getFactoryMacrosFolder ());
		if(factoryRevision < 0)
			factoryRevision = 0; // force copy when both don't exist (theroretical case, we _have_ a factory revision in our library)

		if(factoryRevision > userRevision)
			this.copyFactoryMacrosTo (userPath);

		// load page file contents into memory, their macros will be scanned in rescanAll
		this.loadPageFilesToImport ();

		// initial macro scan
		this.rescanAll ();
	}

	this.rescanAll = function ()
	{
		// remove all macros, but keep a temp copy of the array (does not copy the macro objects)
		let oldMacros = this.macros.slice ();
		this.macros.length = 0;
		
		// scan for user macros
		let userPath = this.getMacrosFolder ();		
		this.scanForMacros (userPath, false);

		// scan for macros in additional read-only locations
		let readFolders = this.getAdditionalReadFolders ();
		if(readFolders)
			for(let f in readFolders)
			{
				let folderItem = readFolders[f];
				this.scanForMacros (folderItem.path, true);
			}

		// sort alphabetically by 1.) group, 2.) title
		this.macros.sort (function (a, b) {
			let result = a.group.localeCompare (b.group);
			return result != 0 ? result : a.title.localeCompare (b.title);
		});

		// collect macros, register / update commands
		for(let i in this.macros)
		{
			let macro = this.macros[i];
			let commandName = this.makeCommandName (macro);
			let commandTitle = macro.title;
			let commandEnglishName = macro.title;

			// check if a macro with the same id existed before
			if(oldMacros.some (function (element, index, array) { return element.id == macro.id }))
			{
				// update command display name
				let command = Host.GUI.Commands.findCommand (kMacrosCategory, commandName);
				if(command)
					command.displayName = commandTitle;
			}
			else
				Host.GUI.Commands.registerCommand (kMacrosCategory, commandName, JSTRANSLATE ("Macros"), commandTitle, commandEnglishName);
		}

		// unregister old macros that disappeared
		for(let i in oldMacros)
		{
			let macro = oldMacros[i];
			if(!this.macros.some (function (element, index, array) { return element.id == macro.id }))
			{
				let commandName = this.makeCommandName (macro);
				Host.GUI.Commands.unregisterCommand (kMacrosCategory, commandName);
			}
		}
		
		// emit global signal
		Host.Signals.signal (kMacrosSignal, kMacrosRescanned)
	}
	
	this.copyFactoryMacrosTo = function (userPath)
	{
		let factoryPath = this.getFactoryMacrosFolder ();		
		let iter = Host.IO.findFiles (factoryPath, "*." + theMacroFileType.extension);
		while(!iter.done ())
		{
			let srcPath = iter.next ();
			
			let destPath = Host.Url (userPath);
			destPath.descend (srcPath.name);
			
			Host.IO.File (srcPath).copyTo (destPath);
		}

		// copy revision file
		let srcPath = this.getRevisionFile (factoryPath);
		let destPath = this.getRevisionFile (userPath);
		Host.IO.File (srcPath).copyTo (destPath);
	}

	this.loadPageFilesToImport = function (folderPath, readOnly)
	{
		// scan for page files in read-only locations and copy their contents (macro files + macopage.xml) into memory locations
		let pageFiles = this.collectPageFilesToImport ();
		for(let p in pageFiles)
		{
			let pageFile = pageFiles[p];
			let locationId = pageFile.id;

			// copy full page zip contents into memory folder: for scanning macros from there and importing page
			let packageFile = Host.IO.openPackage (pageFile.path, "application/zip");
			if(packageFile)
			{
				let pageTargetFolder = this.getMacrosMemoryFolder (locationId);
				packageFile.extract (pageTargetFolder);

				// keep list of extracted page files for later import
				this.extractedPageFiles.push ({id: locationId, extractedFolder: pageTargetFolder});

				// add location for scanning macros of page
				let extensionHandler = this.getExtensionHandler ();
				if(extensionHandler)
					extensionHandler.addLocation (locationId, pageTargetFolder);

				//Host.Console.writeLine ("Extract readonly page content: " + pageFile.path.url + " ->  " + pageTargetFolder.url);
			}
			else
				Host.GUI.alert (JSTRANSLATE ("The file is empty or corrupt and could not be imported."));
		}
	}

	this.scanForMacros = function (folderPath, readOnly)
	{
		var iter = Host.IO.findFiles (folderPath, "*." + theMacroFileType.extension);
		while(!iter.done ())
		{
			let macroPath = iter.next ();
			
			let macro = new Macro;
			if(macro.loadFromFile (macroPath))
			{
				macro.originalPath = macroPath;
				macro.id = this.makeMacroID (macroPath);
				macro.readOnly = readOnly;
				this.macros.push (macro);
			}
		}
	}
	
	this.duplicateMacro = function (macro)
	{
		// copy macro file
		let destMacroPath = Host.Url (macro.originalPath);
		if(macro.readOnly)
		{
			destMacroPath = this.getMacrosFolder ();
			destMacroPath.descend (macro.originalPath.name);
		}
		destMacroPath.makeUnique ();

		//Host.Console.writeLine ("duplicateMacro: " + destMacroPath.url);
		Host.IO.File (macro.originalPath).copyTo (destMacroPath);

		// make unique title (in duplicated macro file content)
		let newMacro = new Macro;
		if(newMacro.loadFromFile (destMacroPath))
		{
			let baseTitle = newMacro.title;

			let bracketIndex = baseTitle.lastIndexOf ("(");
			if(bracketIndex >= 0)
				baseTitle = baseTitle.substr (0, bracketIndex);

			for(let i = 2; true; i++)
			{
				title = baseTitle + "(" + i + ")";
				if(this.macros.every (function (element, index, array) { return element.title != title }) || i > 100)
					break;
			}

			newMacro.title = title;
			newMacro.saveToFile (destMacroPath);
		}

		this.rescanAll ();
		return this.getMacroByPath (destMacroPath);
	}

	this.renameMacroFile = function (macro, newName)
	{
		let oldMacroID = this.makeMacroID (macro.originalPath);
		let newFileName = this.makeMacroFileName (newName);

		let newPath = Host.Url (macro.originalPath);
		newPath.ascend ();
		newPath.descend (newFileName);
		newPath.makeUnique ();

		if(Host.IO.File (macro.originalPath).moveTo (newPath))
		{
			macro.originalPath = newPath;
			macro.id = this.makeMacroID (macro.originalPath);

			Host.Signals.signal (kMacrosSignal, kMacroRenamed, macro, oldMacroID);

			// get key bindings from old command
			let oldCommandName = this.makeCommandNameFromID (oldMacroID);
			let oldCommand = Host.GUI.Commands.findCommand (kMacrosCategory, oldCommandName);

			let keys = [];
			let bindingsIter = Host.GUI.Commands.lookupBindings (oldCommand);
			if(bindingsIter)
				while(!bindingsIter.done ())
					keys.push (bindingsIter.next ());

			this.rescanAll ();

			// after rescan, old command is now removed, new command registered
			if(keys.length != 0)
			{
				let newCommandName = this.makeCommandName (macro);
				let newCommand = Host.GUI.Commands.findCommand (kMacrosCategory, newCommandName);
				if(newCommand)
				{
					for(let i in keys)
					{
						let key = keys[i];
						Host.GUI.Commands.assignKey (newCommand, key);
					}
				}
			}
			return true;
		}
		return false;
	}

	this.buildMenu = function (menu, commandHandler)
	{
		// build groups
		var groups = new Array;
		for(let i in this.macros)
		{
			var macro = this.macros[i];
			var key = macro.group;
			if(groups[key] == undefined)
				groups[key] = new Array;
			groups[key].push (macro);			
		}
		
		let useSubMenu = this.macros.length > 20;
		
		// create sorted list of keys
		var keys = new Array;
		for(let key in groups)
			keys.push (key);
		keys.sort ();
						
		for(let i in keys)
		{
			var key = keys[i];
			
			// sort macros in group alphabetically
			groups[key].sort (function (a, b) {
				return a.title.localeCompare (b.title);
			});
						
			// add header or submenu
			let parentMenu = menu;
			if(key.length > 0)
			{
				if(useSubMenu)
				{
					parentMenu = menu.createMenu ();
					parentMenu.title = key;
					menu.addMenu (parentMenu);
				}
				else
					menu.addHeaderItem (key);
			}

			// add to menu
			for(let i in groups[key])
			{
				var macro = groups[key][i];
				var commandName = this.makeCommandName (macro)
				parentMenu.addCommandItem (macro.title, kMacrosCategory, commandName, commandHandler);
			}
		}
	}

	this.makeMacroID = function (macroPath)
	{
		let fileName = macroPath.name;
		let dotIndex = fileName.lastIndexOf (".");
		fileName = fileName.substring (0, dotIndex);
		
		// e.g. "presonus.ampire.extras-VEVTVCBNQUNSTzE="
		let id = this.getFolderID (macroPath);
		if(id != "")
			id += "-";
		
		id += Host.IO.toBase64 (fileName);
		return id;
	}

	this.makeMacroPathFromID = function (macroId)
	{
		let folder = null;

		let minusIndex = macroId.lastIndexOf ("-");
		if(minusIndex > 0)
		{
			let folderId = macroId.substring (0, minusIndex);
			macroId = macroId.substring (minusIndex + 1);

			let handler = this.getExtensionHandler ();
			if(handler)
				folder = handler.getFolderByID (folderId);
		}
		if(folder == null)
			folder = this.getMacrosFolder ();
			
		let title = Host.IO.fromBase64 (macroId);
		let fileName = this.makeMacroFileName (title);
		let macroUrl = Host.Url (folder);
		macroUrl.descend (fileName);
		return macroUrl;
	}

	this.macroExists = function (macroId)
	{
		let macroPath = this.makeMacroPathFromID (macroId);
		return Host.IO.File (macroPath).exists ();
	}

	this.makeCommandName = function (macro)
	{
		return "Macro " + macro.id;
	}

	this.makeCommandNameFromID = function (id)
	{
		return "Macro " + id;
	}

	this.makeMacroFileName = function (title)
	{
		return CCL.JS.LegalFileName (title + "." + theMacroFileType.extension);
	}

	this.getMacroForCommand = function (commandName)
	{
		let macroID = commandName.substring (6); // "Macro xx"
		return this.getMacroByID (macroID);
	}

	this.getMacroByID = function (macroID)
	{
		for(let i in this.macros)
		{
			var macro = this.macros[i];
			if(macro.id == macroID)
				return macro;
		}
		return null;
	}

	this.getMacroByPath = function (macroPath)
	{
		let id = this.makeMacroID (macroPath);
		return this.getMacroByID (id);
	}
}

var theMacroManager = new MacroManager;
