include_file("resource://{main}/sdk/cclapp.js");
include_file ("elements.js");
include_file ("renamer.js");
include_file ("shared.js");
include_file ("panel.js");

//////////////////////////////////////////////////////////////////////////////////////////////////
// Class factory entry point
//////////////////////////////////////////////////////////////////////////////////////////////////

function createInstanceSong (args)
{
	__init (args); // init package identifier

	return new StudioOneMacroPanel ("Arrangement", JSTRANSLATE ("Arrangement"), true);
}

//////////////////////////////////////////////////////////////////////////////////////////////////

function createInstanceMusicEditor (args)
{
	return new StudioOneMacroPanel ("MusicEditor", JSTRANSLATE ("Note Editor"));
}

//////////////////////////////////////////////////////////////////////////////////////////////////

function createInstanceAudioEditor (args)
{
	return new StudioOneMacroPanel ("AudioEditor", JSTRANSLATE ("Audio Editor"));
}

//////////////////////////////////////////////////////////////////////////////////////////////////

function createInstanceProject (args)
{
	__init (args); // init package identifier

	return new StudioOneMacroPanel ("Project", JSTRANSLATE ("Project"), true);
}

//////////////////////////////////////////////////////////////////////////////////////////////////

function createInstanceShow (args)
{
	__init (args); // init package identifier

	return new StudioOneMacroPanel ("Show", JSTRANSLATE ("Show"), true);
}
