
const kCommandBarFile = "commandbar-v3.xml";
const kCommandBarFilePattern = "commandbar-v*.xml";
const kCommandBarFileVersion = 3;
const kLegacyCommandBarFile = "commandbar.xml";
const kMacroPageFile = "macropage.xml";

let theMacroBar = null; // global shared instance
let backupDone = false;

StudioOneMacroPanel.prototype = new CCL.JS.Component (); // inherit from CCL.JS.Component
function StudioOneMacroPanel (name, title, isMainInstance)
{
	this.interfaces.push (Host.Interfaces.IViewStateHandler);
	this.name = name;
	this.title = title;
	this.isMainInstance = isMainInstance;

	this.commandHandler = new CommandHandlerDelegate (this);
	this.contextMenuHandler = new ContextMenuHandlerDelegate (this);
	this.commandTargets = new Array;
	this.numStaticTargets = 0;

	this.kMacroFileExtension = ".studioonemacro";
	this.selectedPageIndex = 0;
	this.verticalOrientation = false;

	this.initialize = function (context)
	{	
		// call super class method
		CCL.JS.Component.prototype.initialize.call (this, context);
		
		// get macro manager from service, must not fail!
		this.macroManager = getSharedMacroManager ();

		// load event names
		theEventRenamer.startup ();
		
		with(this.paramList)
		{
			let frameTitle = JSTRANSLATE ("Macros");
			frameTitle += " (";
			frameTitle += title;
			frameTitle += ")";
			addString ("frameTitle").setValue (frameTitle);

			addMenu ("renameMenu");
			addMenu ("editMenu");
			addMenu ("setupMenu");
		}
		this.addTarget ("renameMenu", JSTRANSLATE ("Name"))
		this.addTarget ("editMenu", JSTRANSLATE ("Action"))
		this.addTarget ("setupMenu", JSTRANSLATE ("Setup"))
//		this.addTarget ("pageMenu", JSTRANSLATE ("Pages"))

		this.numStaticTargets = this.commandTargets.length
		this.updateMacroTargets ();

		// create command bar (first time) or share existing
		if(theMacroBar == null)
		{
			theMacroBar = this.createCommandBar ();
			this.macroBar = theMacroBar;
			this.loadCommandBar ();

			// register page commands (only once)
			Host.GUI.Commands.registerCommand ("View", "Previous Macro Page", JSTRANSLATE ("View"), JSTRANSLATE ("Previous Macro Page"), "Previous Macro Page");
			Host.GUI.Commands.registerCommand ("View", "Next Macro Page", JSTRANSLATE ("View"), JSTRANSLATE ("Next Macro Page"), "Next Macro Page");
			Host.GUI.Commands.registerCommand ("View", "Select Macro Page", JSTRANSLATE ("View"), JSTRANSLATE ("Select Macro Page"), "Select Macro Page", "Name");
		}
		else
			this.macroBar = theMacroBar;

		// restore selected page
		let pageIndex = Host.Settings.getAttributes ("MacroToolBar").getAttribute (this.getSettingsID (".page"));
		if(pageIndex != null)
			this.selectPage (pageIndex);

		// add dependencies
		Host.Signals.advise (kMacrosSignal, this);
		
		return Host.Results.kResultOk;
	}

	this.terminate = function ()
	{
		// remove dependencies
		Host.Signals.unadvise (kMacrosSignal, this);

		// save selected page
		Host.Settings.getAttributes ("MacroToolBar").setAttribute (this.getSettingsID (".page"), this.selectedPageIndex);

		// save commandbar to file
		this.saveCommandBar ();

		// call super class method
		CCL.JS.Component.prototype.terminate.call (this);
	}

	this.getSettingsID = function (suffix)
	{
		return this.name + suffix;
	}

	// IViewStateHandler
	this.saveViewState = function (viewID, viewName, attributes)
	{
		// saved in workspace state (song)
		attributes.setAttribute ("vertical", this.verticalOrientation);
		return true;
	}

	this.loadViewState = function (viewID, viewName, attributes)
	{
		this.verticalOrientation = attributes.getAttribute ("vertical");
		return true;
	}

	this.getSelectedPage = function ()
	{
		return this.macroBar.getPage (this.selectedPageIndex);
	}

	this.selectPage = function (pageIndex)
	{
		this.selectedPageIndex = pageIndex;
	}

	this.onSelectPage = function (msg)
	{
		if(msg.checkOnly)
			return;

		// note: don't confuse command "arguments" with  message "args"
		let commandArgs = msg.arguments;
		let name = commandArgs ? commandArgs.getAttribute ("Name") : "";
		if(name == "")
			return;

		// find page with given title
		let numPages = this.macroBar.countPages ();
		for(let i = 0; i < numPages; i++)
		{
			let page = this.macroBar.getPage (i);
			if(page && page.title == name)
			{
				this.selectPage (i);
				this.macroBar.invalidate ();
				break;
			}
		}
	}

	this.selectNextPage = function (delta)
	{
		let numPages = this.macroBar.countPages ();
		let pageIndex = this.selectedPageIndex + delta;

		// wrap around
		if(pageIndex < 0)
			pageIndex = numPages - 1;
		else if(pageIndex >= numPages)
			pageIndex = 0;
		
		this.selectPage (pageIndex);
		this.macroBar.invalidate ();
	}

	this.createCommandBar = function ()
	{
		let commandBar = ccl_new ("CCL:CommandBarModel");
        commandBar.getRootItem ().acceptedChildClasses = "CommandBar.Page,CommandBar.SetupGroup";
        return commandBar;
	}

	this.addTarget = function (name, title, category, icon)
	{
		this.commandTargets.push (this.createTarget (name, title, category, icon));
	}

	this.createTarget = function (_name, _title, _category, _icon)
	{
		var target = {name: _name, title: _title , category: _category}
		if(_icon)
		{
			var icon = this.getTheme ().getImage (_icon);
			target.icon = icon;
		}
		return target;
	}
	
	this.updateMacroTargets = function ()
	{
		// remove params and targets before the static ones
		for(let i = 0; i < this.commandTargets.length - this.numStaticTargets; i++)
		{
			let target = this.commandTargets[i];
			this.paramList.remove (target.name);
		}
		this.commandTargets.splice (0, this.commandTargets.length - this.numStaticTargets)

		// add new targets and params before the static ones
		let index = 0;
		for(let i in this.macroManager.macros)
		{
			let macro = this.macroManager.macros[i];
			let commandName = this.macroManager.makeCommandName (macro);
			let category = JSTRANSLATE ("Macros");
			if(macro.group != "")
				category += "/" + macro.group;
			
			this.commandTargets.splice (index, 0, this.createTarget (commandName, macro.title, category, macro.icon));
			this.paramList.addCommand ("Macros", commandName, commandName);
			index++;
		}
	}

	this.traverseItems = function (parent, visitFunc)
	{
		let numChilds = parent.numChilds;
		for(let i = 0; i < numChilds; i++)
		{
			let child = parent.getChildItem (i);

			visitFunc (child);
			this.traverseItems (child, visitFunc);
		}

		let menuContent = parent.menuContent;
		if(menuContent)
			this.traverseItems (menuContent, visitFunc);
	}

	this.saveCommandBar = function (withBackup)
	{
		// save commandbar to file (only one panel instance per song needs to do it)
		if(this.isMainInstance)
		{
			let userPath = this.macroManager.getMacrosFolder ();
			userPath.descend (kCommandBarFile);
	
			if(withBackup && !backupDone)
			{
				// save the previous file as a backup on the first edit (overwrite the previous backup only once per session)
				let backupPath = this.macroManager.getMacrosFolder ();
				backupPath.descend (kCommandBarFile + ".bak");

				if(Host.IO.File (userPath).exists ())
				{
					Host.IO.File (userPath).copyTo (backupPath);
					backupDone = true;
				}
			}
			this.macroBar.saveToFile (userPath); 
		}
	}

	this.loadCommandBar = function (noMigration)
	{
		let tempPath = this.macroManager.getMacrosFolder ();
		tempPath.descend ("__temp__", true);
		if(Host.IO.File (tempPath).exists ())
			Host.IO.File (tempPath).remove (false);

		let factoryMacroBarFile = CCL.JS.ResourceUrl (kCommandBarFile);

		// path in user folder
		let userPath = this.macroManager.getMacrosFolder ();
		userPath.descend (kCommandBarFile);

		let commandBarExists = Host.IO.File (userPath).exists ();

		if(!commandBarExists)
		{
			// try previous versioned file name (2 was the first)
			for(let version = kCommandBarFileVersion - 1; version >= 2; version--)
			{
				let fileName = kCommandBarFilePattern;
				fileName = fileName.replace ("*", version);

				let oldPath = this.macroManager.getMacrosFolder ();
				oldPath.descend (fileName);

				if(Host.IO.File (oldPath).exists ())
				{
					userPath = oldPath;
					commandBarExists = true; // read "v2 or later"
					break;
				}
			}
		}

		let commandBarLoaded = false;
		if(commandBarExists)
			commandBarLoaded = this.macroBar.loadFromFile (userPath);

		// copy factory bar from resources at first time, or if load failed
		if(!commandBarLoaded)
		{
			Host.IO.File (factoryMacroBarFile).copyTo (userPath);
			commandBarLoaded = this.macroBar.loadFromFile (userPath);
		}

		if(!noMigration)
		{
			if(!commandBarExists) // but legacy file might exist
			{
				// special handling for old commandbar file from Studio One 3 (no pages)
				let legacyPath = this.macroManager.getMacrosFolder ();
				legacyPath.descend (kLegacyCommandBarFile);
				if(Host.IO.File (legacyPath).exists ())
				{
					let root = this.macroBar.getRootItem ();
					if(root != null)
					{
						let firstPage = root.getChildItem (1);
						if(firstPage != null)
						{
							// remove the first page because it will be replaced by the macrobar from version 3
							firstPage.removeAll ();
								
							let legacyBar = this.createCommandBar ();
							if(legacyBar != null)
							{
								legacyBar.loadFromFile (legacyPath);
								for(let i = 0; i < legacyBar.getRootItem ().numChilds; i++)
								{
									let group = legacyBar.getRootItem ().getChildItem (i);
									if(group.type == "Group")
									{
										let numChilds = group.numChilds;
										for(let a = 0; a < numChilds; a++)
										{
											let button = group.getChildItem (a);
											if(button.type == "Menu" && button.commandName == "setupMenu")
											{
												group.removeChildItem (button);
												a--;
												numChilds--;
											}
										}
									}
									this.macroBar.getRootItem ().getChildItem (1).addChildItem (group);
								}
							}

							this.macroBar.saveToFile (userPath);
						}
					}
				}
			}

			let factoryBar = this.createCommandBar ();
			factoryBar.loadFromFile (factoryMacroBarFile);
			let isNewRevision = this.macroBar.getRootItem ().revision == null || factoryBar.getRootItem ().revision != null && this.macroBar.getRootItem ().revision < factoryBar.getRootItem ().revision;

			if(!commandBarExists || isNewRevision)
			{
				let macrosResourceFolder = CCL.JS.ResourceUrl ("/library", true);
				let searchPattern = "*.studioonemacro";
				let fileIterator = Host.IO.findFiles (macrosResourceFolder, searchPattern);

				let file = fileIterator.next ();
				while(file != null)
				{
					let legacyPath = this.macroManager.getMacrosFolder ();
					legacyPath.descend (file.name);
					if(!Host.IO.File (legacyPath).exists ())
						Host.IO.File (file).copyTo (legacyPath);
					
					file = fileIterator.next ();
				}
				
				this.macroManager.rescanAll ();
				this.updateMacroTargets ();
			}

			if(isNewRevision)
			{
				// collect factory groups with their page titles
				let factoryGroups = {};
				let setupGroup = null;
				for(let i = 0; i < factoryBar.getRootItem ().numChilds; i++)
				{
					// page 0: setup group
					let factoryPage = factoryBar.getRootItem ().getChildItem (i);
					if(factoryPage.type == "SetupGroup")
					{
						setupGroup = factoryPage;
						continue;
					}

					// groups in page
					let numGroups = factoryPage.numChilds;
					for(let g = 0; g < numGroups; g++)
					{
						let group = factoryPage.getChildItem (g);
						if(group.type == "Group")
						{
							if(group.revision > 0)
								factoryGroups[group.title] = { "group" : group, "pageTitle": factoryPage.title };
							else
								Host.Console.writeLine ("Factory group must have revision: " + factoryPage.title +" - " + group.title );
						}
					}
				}

				// user pages:
				for(let i = 0; i < this.macroBar.getRootItem ().numChilds; i++)
				{
					// page 0: setup group
					let page = this.macroBar.getRootItem ().getChildItem (i);
					if(page.type == "SetupGroup")
					{
						let setupGroupRevision = page.revision;
						if(setupGroupRevision == null || setupGroupRevision < setupGroup.revision)
						{
							this.macroBar.getRootItem ().removeChildItem (page);
							this.macroBar.getRootItem ().addChildItem (setupGroup, 0);
						}
						continue;
					}

					// Remove the "Page 1 - " prefix that appeared in previous factory page titles; we want them to match the new plain titles
					page.title = page.title.replace (RegExp ('^Page [0-9]+ - '), '');

					// groups in page:
					let numGroups = page.numChilds;
					for(let g = 0; g < numGroups; g++)
					{
						let group = page.getChildItem (g);
						let factoryGroup = factoryGroups[group.title];
						//Host.Console.writeLine ("group: " + group.title + "  rev ." + group.revision);

						if(group.type == "Group" && factoryGroup != null)
						{
							//Host.Console.writeLine ("    factoryGroup: " + factoryGroup.group.title + "  rev ." + factoryGroup.group.revision + " (" + factoryGroup.pageTitle +")");
							if(group.revision != null && group.revision != 0 && factoryGroup.group.revision > group.revision)
							{
								page.removeChildItem (group);
								page.addChildItem (factoryGroup.group, g);
							}
							factoryGroups[factoryGroup.group.title] = null;
						}
					}
				}

				// add remaining (new) factory groups as new groups to existing or new pages
				for(let fgTitle in factoryGroups)
				{
					let factoryGroup = factoryGroups[fgTitle];
					if(factoryGroup != null)
					{
						let groupAdded = false;
						for(let i = 0; i < this.macroBar.getRootItem ().numChilds; i++)
						{
							let page = this.macroBar.getRootItem ().getChildItem (i);
							if(page.title == factoryGroup.pageTitle)
							{
								//Host.Console.writeLine ("add new factoryGroup: " + factoryGroup.group.title + " to page: " + + page.title);
								page.addChildItem (factoryGroup.group);
								groupAdded = true;
							}
						}
						if(!groupAdded)
						{
							let newPage = this.macroBar.createPage ();
							newPage.title = factoryGroup.pageTitle;
							newPage.addChildItem (factoryGroup.group);
							this.macroBar.getRootItem ().addChildItem (newPage);
							//Host.Console.writeLine ("new page for factoryGroup: " + factoryGroup.group.title + ": " + newPage.title);
						}
					}
				}

				this.macroBar.getRootItem ().revision = factoryBar.getRootItem ().revision;
			}

			// check if the setup group exists (should be page 0)
			let setupGroup = null;
			let hasSetupGroup = false;
			for(let i = 0; i < this.macroBar.getRootItem ().numChilds; i++)
			{
				let page = this.macroBar.getRootItem ().getChildItem (i);
				if(page.type == "SetupGroup")
				{
					hasSetupGroup = true;
					setupGroup = page;
					break;
				}
			}
			if(!hasSetupGroup)
			{
				// add missing setup group
				for(let i = 0; i < factoryBar.getRootItem ().numChilds; i++)
				{
					let factoryPage = factoryBar.getRootItem ().getChildItem (i);
					if(factoryPage.type == "SetupGroup")
					{
						this.macroBar.getRootItem ().addChildItem (factoryPage, 0);
						setupGroup = factoryPage;
						Host.Console.writeLine ("Restored missing setup group");
						break;
					}
				}
			}
			// modify the setupMenu button to use context menu on left click
			if(setupGroup != null)
			{
				let numChilds = setupGroup.numChilds;
				for(let a = 0; a < numChilds; a++)
				{
					let button = setupGroup.getChildItem (a);
					if(button.type == "Menu" && button.commandName == "setupMenu")
						button.isLeftClickContextMenu = true;
				}
			}
		}

		this.importReadOnlyPages ();
		this.checkMissignMacros ();
		this.selectPage (0);
	}

	this.importReadOnlyPages = function ()
	{
		for(let f in this.macroManager.extractedPageFiles)
		{
			let folderItem = this.macroManager.extractedPageFiles[f];
			let contentFolder = folderItem.extractedFolder;

			// load page item from xml file
			let pageFile = Host.Url (contentFolder);
			pageFile.descend (kMacroPageFile);
			let pageItem = this.macroBar.loadItemFromFile (pageFile);
			let macroButtons = this.getMacroButtons (pageItem);

			// adjust macro buttons if they refer to macros of the page file (now in memory folder)
			for(let i = 0; i < macroButtons.length; i++)
			{
				let button = macroButtons[i];
				let fullName = Host.IO.fromBase64 (button.commandName.substr (6));
				let macroUrl = Host.Url (contentFolder);
				macroUrl.descend (fullName + this.kMacroFileExtension);

				if(Host.IO.File (macroUrl).exists ())
				{
					button.commandName = "Macro " + this.macroManager.makeMacroID (macroUrl);
					//Host.Console.writeLine ("Macro from page: " + button.commandName + " -> " + fullName);
				}
			}

			this.macroBar.getRootItem ().addChildItem (pageItem);
			pageItem.isTemporary = true;
			pageItem.isReadOnly = true;
		}
		this.macroBar.checkItemsIDs ();
		this.updateMacroTargets ();
	}

	this.countTemporaryPages = function (id)
	{
		let count = 0;

		let numPages = this.macroBar.countPages ();
		for (let i = 0; i < numPages; i++)
			if(this.macroBar.getPage (i).isTemporary)
				count++;

		return count;
	}

	this.checkMissignMacros = function ()
	{
		let panel = this;
		this.traverseItems (this.macroBar.getRootItem (),
			function (item)
			{
				if(item.type === "Button" && item.commandName.indexOf ("Macro ") == 0)
				{
					let macroId = item.commandName.substr (6);
					if(!panel.macroManager.macroExists (macroId))
					{
						let itemInfo = "\""
						let parentItem = panel.macroBar.getParentItem (item);
						if(parentItem)
							itemInfo += parentItem.title + "\" - \"";
						itemInfo += item.title + "\"";

						Host.Console.writeLine (JSTRANSLATE ("Macro not found:") + " \"" + panel.macroManager.makeMacroPathFromID (macroId).url + "\" (" + itemInfo + ")");
					}
				}
			});
	}

	this.onCommand = function (category, name)
	{
		// try in active editor
		var activeEditor = this.context.activeEditor;
		if(activeEditor)
		{
			if(activeEditor.interpretCommand (category, name))
				return true;
		}

		// interpret macro command
		if(category == "Macros")
		{
			let macro = this.macroManager.getMacroForCommand (name);
			if(macro)
			{
				this.executeMacro (macro);
				return true;
			}
		}
				
		return false;
	}
	
	this.executeMacro = function (macro)
	{
		(new MacroExecuter (macro, this.context.activeEditor)).execute ();
	}
	
	this.onRenameEvents = function (eventName)
	{
		var macro = new Macro;
		
		var c = macro.addCommand ("Event", "Rename Events");
		c.addArgument ("New Name", eventName);
		c.addArgument ("Add numbers", true);
		
		this.executeMacro (macro);
	}
	
	this.onResetToolbar = function ()
	{
		if(Host.GUI.ask (JSTRANSLATE ("Are you sure you want to revert all changes?")) != Host.GUI.Constants.kYes)
			return;

		// save current state as backup
		let backupPath = this.macroManager.getMacrosFolder ();
		backupPath.descend (kCommandBarFile + ".bak");
		this.macroBar.saveToFile (backupPath);

		// remove file in user folder
		let userPath = this.macroManager.getMacrosFolder ();
		userPath.descend (kCommandBarFile);

		Host.IO.File (userPath).remove ();

		// copy factory file from resources
		let factoryMacroBarFile = CCL.JS.ResourceUrl (kCommandBarFile);
		Host.IO.File (factoryMacroBarFile).copyTo (userPath);

		this.loadCommandBar (true);
	}

	this.onEditNames = function ()
	{
		var nameEditor = new EventNameEditor;
		nameEditor.initialize ();
		nameEditor.loadFromFile (theEventRenamer.getNamesFile ());
		if(nameEditor.runDialog () == Host.GUI.Constants.kOkay)
		{
			nameEditor.saveToFile (theEventRenamer.getNamesFile ());
			
			theEventRenamer.reloadAll ();
		}
		nameEditor.terminate ();
	}
	
	this.paramChanged = function (param) {}
	
	this.onExtendMenu = function (param, menu)
	{
		if(param.name == "renameMenu")
		{
			theEventRenamer.buildMenu (menu, new RenameCommandHandler (this));
		}
		else if(param.name == "editMenu")
		{
			this.macroManager.buildMenu (menu, this);
		}
		else if(param.name == "setupMenu")
		{
			// todo: comment in "Help" command, when it is possible to open open help with macro context...
			// menu.addCommandItem (JSTRANSLATE ("Help"), kMacrosCategory, "Help", this);
			menu.addCommandItem (JSTRANSLATE ("Macro Organizer"), "Gadgets", "Macro Organizer"); // handled by macro gadget
			//menu.addSeparatorItem ();
			// menu.addCommandItem (JSTRANSLATE ("Edit Names"), kMacrosCategory, "Edit Names", this);
			// menu.addCommandItem (JSTRANSLATE ("Reload Names"), kMacrosCategory, "Reload Names", this);
			//menu.addSeparatorItem ();
			menu.addCommandItem (JSTRANSLATE ("Reset Toolbar"), kMacrosCategory, "Reset Toolbar", this);
		}
	};

	this.onContextMenu = function (contextMenu)
	{
		let item = contextMenu.focusItem;

		let mainGroup = this.macroBar.getRootItem ().getChildItem (0);

		var isRootOrMain = this.macroBar.getRootItem () == item || item.type === "SetupGroup";
		var isPage = item.type === "Page";
		var isPartOfMainGroup = this.macroBar.getParentItem (item) == mainGroup;
		var isSetupButton = item.type === "Menu" && item.commandName == "setupMenu";

		if(isRootOrMain || isPartOfMainGroup)
			item = this.getSelectedPage ();

		this.contextMenuTargetItem = item;

		if(isRootOrMain || isPage || isPartOfMainGroup)
		{
			contextMenu.addSeparatorItem ();
			contextMenu.addCommandItem (JSTRANSLATE ("Import..."), kMacrosCategory, "Import Page", this);
			contextMenu.addCommandItem (JSTRANSLATE ("Export..."), kMacrosCategory, "Export Page", this);
		}
		if(isSetupButton)
		{
			contextMenu.addSeparatorItem ();
			contextMenu.addCommandItem (JSTRANSLATE ("Macro Organizer"), "Gadgets", "Macro Organizer", 0);
			contextMenu.addCommandItem (JSTRANSLATE ("Reset Toolbar"), kMacrosCategory, "Reset Toolbar", this);
		}
	}

	this.checkCommandCategory = function (category)
	{
		return category == kMacrosCategory || category == "View";
	}

	this.calcMacroFileHash = function (path)
	{
		let textFile = Host.IO.openTextFile (path);
		let content = "";
		while(!textFile.endOfStream)
			content += textFile.readLine ();

		textFile.close ();

		let hash = 0;
		for(let i = 0; i < content.length; i++)
			hash  = ((hash << 5) - hash + content.charCodeAt(i)) << 0;
		
		return hash;
	}

	this.getAvailableMacroFiles = function (path)
	{
		let files = {};

		let searchPattern = "*.studioonemacro";
		let fileIterator = Host.IO.findFiles (path, searchPattern);

		let file = fileIterator.next ();
		while(file != null)
		{
			let hash = this.calcMacroFileHash (file);

			let name = file.name;
			let suffix = ".studioonemacro";
			if(name.indexOf(suffix, name.length - suffix.length) !== -1) // name ends with suffix
				name = name.substr (0, name.length - suffix.length);

			files[name] = hash;

			file = fileIterator.next ();
		}

		return files;
	};

	this.getMacroButtons = function (item)
	{
		let macroButtons = [];

		this.traverseItems (item,
			function (item)
			{
				if(item.type === "Button" && item.commandName.indexOf ("Macro ") == 0)
					macroButtons.push (item);
			});

		return macroButtons;
	};

	this.deduplicateMacroNames = function (name, hash, availableFiles, button)
	{
		let openBrace = name.indexOf ("__(");
		if(name.indexOf(this.kMacroFileExtension, name.length - this.kMacroFileExtension.length) !== -1)
			name = name.substr (0, name.length - this.kMacroFileExtension.length);
		if(openBrace > -1)
			name = name.substr (0, openBrace);

		let newName = name;
		let copy = true;
		// try to find an available macro with the same content and use it instead of copying
		for(let availableName in availableFiles)
		{
			if(availableFiles[availableName] == hash)
			{
				newName = availableName;
				copy = false;
			}
		}

		if(copy)
		{
			let newFile = "/" + name;
			let duplicateCounter = 1;
			let currentHash = availableFiles[newName];
			while(currentHash != null)
			{
				newName = name;
				newName += "__(" + (duplicateCounter++) + ")";
				newFile = "/" + newName + this.kMacroFileExtension;
				currentHash = availableFiles[newName];
			}
		}

		let result = Host.IO.toBase64 (newName);
		button.commandName = "Macro " + result;

		return { copy: copy, newName: newName };
	};

	this.onExportPage = function (item)
	{
		if(!item)
			return;

		let fileSelector = ccl_new ("CCL:FileSelector");
		fileSelector.addFilter (theMacroPageFileType);
		fileSelector.setFileName (item.title + "." + theMacroPageFileType.extension);
		fileSelector.runSave (JSTRANSLATE ("Export Macro Page"));
		let path = fileSelector.getPath ();

		if(path == null)
			return;
		
		let packageFile = Host.IO.createPackage (path, "application/zip");
		
		packageFile.setOption ("compressed", true);

		if(!packageFile.create ())
			return false;

		let tempPath = this.macroManager.getMacrosFolder ();
		tempPath.descend ("__temp__", true);

		let availableFiles = this.getAvailableMacroFiles (this.macroManager.getMacrosFolder ());
		let clonedItem = item.cloneItem ();
		let macroButtons = this.getMacroButtons (clonedItem);

		let processedFiles = {};
		for(let i = 0; i < macroButtons.length; i++)
		{
			let button = macroButtons[i];
			let macroId = button.commandName.substr (6);
			let sourceURL = this.macroManager.makeMacroPathFromID (macroId);
			let fullName = sourceURL.getName (false);

			let availableHash = 0;
			if(sourceURL.protocol == "memory")
				availableHash = this.calcMacroFileHash (sourceURL);
			else
				availableHash = availableFiles[fullName];

			if(availableHash != null)
			{
				let result = this.deduplicateMacroNames (fullName, availableHash, processedFiles, button);
				if(result.copy)
				{
					processedFiles[result.newName] = availableHash;

					tempPath.descend (result.newName + this.kMacroFileExtension);
					Host.IO.File (sourceURL).copyTo (tempPath);
					tempPath.ascend ();
				}
			}
		};

		tempPath.descend (kMacroPageFile);
		clonedItem.isTemporary = false;
		clonedItem.isReadOnly = false;
		clonedItem.saveToFile (tempPath);
		tempPath.ascend ();
		packageFile.embedd (tempPath);
		packageFile.flush ();
		packageFile.close ();

		Host.IO.File (tempPath).remove (false);
	};

	this.onImportPage = function ()
	{
		let fileSelector = ccl_new ("CCL:FileSelector");
		fileSelector.addFilter (theMacroPageFileType);
		fileSelector.runOpen (JSTRANSLATE ("Import Macro Page"));

		let path = fileSelector.getPath ();
		this.importPage (path);
	}

	this.importPage = function (path)
	{
		if(path == null)
			return;

		//Host.Console.writeLine ("importPage: " + path.url);
		
		if(Host.IO.File (path).exists ())
		{
			let packageFile = Host.IO.openPackage (path, "application/zip");

			if(packageFile == null)
			{
				Host.GUI.alert (JSTRANSLATE ("The file is empty or corrupt and could not be imported."));
				return;
			}

			let macroTargetFolder = this.macroManager.getMacrosFolder ();

			// extract package, collect macro files
			let extractFolder = Host.Url ("memory://MacroManagerTemp", true); // memory filesystem can only remove a whole "bin"

			packageFile.extract (extractFolder);
			let packageFiles = this.getAvailableMacroFiles (extractFolder);

			// load page item from xml file, collect buttons
			let tempPath = Host.Url (extractFolder);
			tempPath.descend (kMacroPageFile);
			let item = this.macroBar.loadItemFromFile (tempPath);
			let macroButtons = this.getMacroButtons (item);

			// collect existing macros in user folder
			tempPath = this.macroManager.getMacrosFolder ();
			let availableFiles = this.getAvailableMacroFiles (tempPath);

			// copy missing macros to target folder
			for(let i = 0; i < macroButtons.length; i++)
			{
				let button = macroButtons[i];
				let fullName = Host.IO.fromBase64 (button.commandName.substr (6));
				let sourceURL = Host.Url (extractFolder);
				sourceURL.descend (fullName + this.kMacroFileExtension);

				let availableHash = packageFiles[fullName];

				let result = this.deduplicateMacroNames (fullName, availableHash, availableFiles, button);
				if(result.copy)
				{
					let path = Host.Url (macroTargetFolder);
					path.descend (result.newName + this.kMacroFileExtension);

					//Host.Console.writeLine ("Copy page macro " + sourceURL.url + " -> " + path.url);
					// note: cannot move files inside memory filesystem!
					Host.IO.File (sourceURL).copyTo (path);
				}
			}

			Host.IO.File (extractFolder).remove (false);

			this.macroBar.getRootItem ().addChildItem (item);

			let pageItemIndex = this.macroBar.getRootItem ().getChildIndex (item);
			let numTempPages = this.countTemporaryPages ();
			pageItemIndex -= numTempPages; // imported page is now last, but will be before temp pages after after reload

			// path in user folder
			let userPath = this.macroManager.getMacrosFolder ();
			userPath.descend (kCommandBarFile);
			this.macroBar.saveToFile (userPath);
			this.macroManager.rescanAll ();
			this.loadCommandBar (true); // note: temporary pages (excluded on save) will be re-imported here (additional importPage calls)
			this.updateMacroTargets ();
			this.selectPage (pageItemIndex - 1); // page 0 is item 1 (after setup group)
		}
	};
	
	this.interpretCommand = function (msg)
	{
		let result = false;
		if(msg.category == kMacrosCategory)
		{
			switch(msg.name)
			{
			case "Help"         : if(!msg.checkOnly) Host.GUI.Help.showLocation ("studioonemacros"); result = true; break;
			//case "Edit Names" : if(!msg.checkOnly) this.onEditNames (); result = true; break; name editor not finished yet!
			case "Edit Names"	: if(!msg.checkOnly) Host.GUI.openUrl (theEventRenamer.getNamesFile ()); result = true; break;			
			case "Reload Names"	: if(!msg.checkOnly) theEventRenamer.reloadAll (); result = true; break;
			case "Reset Toolbar": if(!msg.checkOnly) this.onResetToolbar (); result = true; break;
			case "Export Page"  : if(!msg.checkOnly) this.onExportPage (this.contextMenuTargetItem); result = true; break;
			case "Import Page"  : if(!msg.checkOnly) this.onImportPage (); result = true; break;

			default : // execute macro
				{
					let macro = this.macroManager.getMacroForCommand (msg.name);
					if(macro)
					{
						if(!msg.checkOnly)
							this.executeMacro (macro);

						result = true;
					}
				}
				break;
			}
		}
		else if(msg.category == "View")
		{
			switch(msg.name)
			{
			case "Previous Macro Page"	: if(!msg.checkOnly) this.selectNextPage (-1); result = true; break;
			case "Next Macro Page"		: if(!msg.checkOnly) this.selectNextPage (+1); result = true; break;
			case "Select Macro Page"	: if(!msg.checkOnly) this.onSelectPage (msg); result = true; break;

			case "Macros":
				{
					// note: a song has 3 different macro panel instances, each with their own window class commands
					// the common command "View - Macros" (also used for Project / Show) delegates to the command for the active editor
					let cmdName = "Macros (Arrangement)";
					let activeEditor = this.context.activeEditor;
					if(activeEditor)
					{
						if(activeEditor.name == "AudioEditor")
							cmdName = "Macros (Audio Editor)";
						else if(activeEditor.name == "MusicEditor")
							cmdName = "Macros (Note Editor)";
					}
					result = Host.GUI.Commands.interpretCommand ("View", cmdName, msg.checkOnly);
				}
			}
		}
		return result;
	}

	this.notify = function (subject, msg)
	{
		if(subject == kMacrosSignal)
		{
			if(msg.id == kMacrosRescanned)
				this.updateMacroTargets ();
			else if(msg.id == kMacroRenamed)
			{
				if(this.isMainInstance) // only one panel instance
				{
					let macro = msg.getArg (0);
					let oldMacroID = msg.getArg (1);
					if(macro)
					{
						// macro file renamed: ID has changed, re-assign affected buttons to the new command name
						let oldCommand = this.macroManager.makeCommandNameFromID (oldMacroID);
						let newCommand = this.macroManager.makeCommandNameFromID (macro.id);

						let root = this.macroBar.getRootItem ();
						if(root)
						{
							let macroButtons = this.getMacroButtons (root);
							for(let i = 0; i < macroButtons.length; i++)
							{
								let button = macroButtons[i];
								if(button.commandName == oldCommand)
								{
									button.commandName = newCommand;
									//Host.Console.writeLine ("remapped button: " + button.title + ": " + button.commandName);
								}
							}					
						}
						this.macroBar.invalidate ();
					}
				}
			}
			else if(msg.id == kImportMacroPage)
			{
				if(this.isMainInstance) // only one panel instance
				{
					let url = msg.getArg (0);
					this.importPage (url);
				}
			}
		}
		else if(msg.id == "ExtendAssignMenu")
		{
			let menu = msg.getArg (0);
			let item = msg.getArg (1);
			if(menu && item && item.type === "Button")
			{
				let handler = new MacroButtonCommandHandler (this, item);
				menu.addCommandItem (JSTRANSLATE ("New Macro..."), kMacrosCategory, "Assign New Macro", handler);
			}
		}
		else if(msg.id == "ExtendButtonMenu")
		{
			let menu = msg.getArg (0);
			let item = msg.getArg (1);
			if(menu && item && item.type === "Button")
			{
				// note: no command category check here (category for macros is "Macros", but was set to empty string on assign due to an old bug)
				let assignedMacro = this.macroManager.getMacroForCommand (item.commandName);
				if(assignedMacro != null)
				{
					let handler = new MacroButtonCommandHandler (this, item);
					if(!assignedMacro.readOnly)
						menu.addCommandItem (JSTRANSLATE ("Edit Macro..."), kMacrosCategory, "Edit Macro", handler);
					menu.addCommandItem (JSTRANSLATE ("Duplicate Macro"), kMacrosCategory, "Duplicate Macro", handler);
					menu.addSeparatorItem ();
				}
			}
		}
		else if(msg.id == CCL.JS.kChanged)
		{
			// automatically save on each macro bar edit
			if(subject == this.macroBar)
				this.saveCommandBar (true);
		}
		else
			CCL.JS.Component.prototype.notify.call (this, subject, msg);
	}
}

function RenameCommandHandler (macroPanel)
{
	this.interfaces = [Host.Interfaces.ICommandHandler];

	// ICommandHandler
	this.checkCommandCategory = function (category)
	{
		return true;
	}
	
	this.interpretCommand = function (msg)
	{
		if(!msg.checkOnly)
			macroPanel.onRenameEvents (msg.name);
		return true;
	}
}

function CommandHandlerDelegate (macroPanel)
{
	this.interfaces = [Host.Interfaces.ICommandHandler];

	// ICommandHandler
	this.checkCommandCategory = function (category)
	{
		return true;
	}

	this.interpretCommand = function (msg)
	{
		if(!msg.checkOnly)
			return macroPanel.onCommand (msg.category, msg.name);
		return true;
	}
}

function ContextMenuHandlerDelegate (macroPanel)
{
	this.interfaces = [Host.Interfaces.IContextMenuHandler];

	this.appendContextMenu = function (contextMenu)
	{
		macroPanel.onContextMenu (contextMenu);

		return Host.Results.kResultOk;
	};
}

//************************************************************************************************
// MacroButtonCommandHandler
/** Handles some shortcut commands for buttons assigned to macros. */
//************************************************************************************************

function MacroButtonCommandHandler (panel, item)
{
	this.interfaces = [Host.Interfaces.ICommandHandler];
	
	this.panel = panel;
	this.item = item;

	this.assignMacroToItem = function (item, macro, macroManager)
	{
		item.title = macro.title;
		item.commandCategory = "";
		item.commandName = macroManager.makeCommandName (macro);
		item.type = 0; // kButton

		this.panel.macroBar.invalidate ();
	}

	// ICommandHandler
	this.checkCommandCategory = function (category)
	{
		return category == kMacrosCategory;
	}

	this.interpretCommand = function (msg)
	{
		if(!msg.checkOnly)
		{
			let macroOrganizer = getMacroOrganizer ();
			let macroManager = getSharedMacroManager ();
			if(macroOrganizer && macroManager)
			{
				if(msg.name == "Assign New Macro")
				{
					// create new macro, assign to button
					let macroID = macroOrganizer.onNewMacro ();
					let newMacro = macroID ? macroManager.getMacroByID (macroID) : 0;
					if(newMacro)
						this.assignMacroToItem (this.item, newMacro, macroManager);
				}
				else if(msg.name == "Edit Macro")
				{
					let commandName = this.item.commandName;
					let macro = macroManager.getMacroForCommand (commandName);
					if(macro)
						macroOrganizer.editMacro (macro);
				}
				else if(msg.name == "Duplicate Macro")
				{
					let commandName = this.item.commandName;
					let macro = macroManager.getMacroForCommand (commandName);
					let parentItem = this.panel.macroBar.getParentItem (this.item);

					if(macro && parentItem)
					{
						let newMacro = macroManager.duplicateMacro (macro);
						if(newMacro)
						{
							// clone button item, assign the new macro
							let newItem = this.item.cloneItem ();
							if(newItem)
							{
								newItem.id = "";
								let index = parentItem.getChildIndex (this.item) + 1;
								this.panel.macroBar.addItem (newItem, parentItem, index);
								this.assignMacroToItem (newItem, newMacro, macroManager);
							}
						}
					}
				}
			}
		}
		return true;
	}
}
