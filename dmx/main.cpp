#include "stdafx.h"
#include <iostream>
#include "dmserializers\idmserializers.h"

void FatalErr(const char* msg) {
	Error(msg);
	EndDMXContext(true);
	CloseHandle(StdOut);
	CloseHandle(StdErr);
	
	TerminateProcess(GetCurrentProcess(),1);
}

void IterateDmxElement(CDmxElement* DmeModelRoot)
{
	for (int i=0;i<DmeModelRoot->AttributeCount();i++)
	{
		CDmxAttribute* pCur = DmeModelRoot->GetAttribute(i);
		CDmxElement* subElem;
 
		Warning( "%s: ",pCur->GetName() );
 
		switch (pCur->GetType())
		{
		case AT_ELEMENT:
			subElem = pCur->GetValue<CDmxElement*>();
			if (subElem)
				IterateDmxElement(subElem);
			break;
 
		case AT_STRING:
			Msg( "STRING | %s\n",pCur->GetValue<CUtlString>().Get() );
			break;
		case AT_INT:
			Msg( "INT | %i\n",pCur->GetValue<int>() );
			break;
		case AT_FLOAT:
			Msg( "FLOAT | %f\n",pCur->GetValue<float>() );
			break;
		case AT_BOOL:
			Msg( "BOOL | %s\n",pCur->GetValue<bool>() ? "true" : "false" );
			break;
 
		default:
			Msg("Unknown type %i\n",pCur->GetType());
			break;
		}
	}
}

CDmxElement* DmeModelRoot = 0;

int CALLBACK WinMain(
  __in  HINSTANCE hInstance,
  __in  HINSTANCE hPrevInstance,
  __in  LPSTR lpCmdLine,
  __in  int nCmdShow
)
{
	if (__argc < 2)
		return 0;

	ifstream fdmx(__argv[1],ios_base::binary);
	if ( fdmx.fail() )
	{
		char* buf = new char[strlen(lpCmdLine) + 30];
		sprintf_s(buf,strlen(lpCmdLine) + 30,"Could not open file (%s)",lpCmdLine);
		Error(buf);
		return 1;
	}

	fdmx.seekg(0,ios_base::end);
	size_t size = fdmx.tellg();
	if ( size <= 0 )
	{
		Error("Invalid file size");
		return 1;
	}

	fdmx.seekg(0);
	char* c_buf = new char[size];
	memset(c_buf,0,size);
	fdmx.read(c_buf,size);

	// validate header
	bool KV2 = (strstr(c_buf,"keyvalues2") != 0);

	char* pos = strstr(c_buf,"format model ");
	int version = 0;
	if (pos)
	{	
		pos += 13;
		int i;
		char ver_str[5];
		for (i=0;i<4;i++)
		{
			if (pos[i] == ' ')
				break;
			ver_str[i] = pos[i];
		}
		ver_str[i] = 0;
		version = atoi(ver_str);
	
		if ( version != 1 && version != 18 )
		{
			char msg[90];
			sprintf_s(msg,"Unrecognised DMX model version (%i). Only '0', 1 and 18 are supported. Continuing anyway...",version);
			Error(msg);
		}
	}
		

	// Allocate
	DECLARE_DMX_CONTEXT();
	DmeModelRoot = (CDmxElement*)DMXAlloc( size + 512 );
	CUtlBuffer v_buf(0,size);
	v_buf.SetExternalBuffer(c_buf,size,size);
	c_buf = 0;
	pos = 0;

	if (KV2)
		DecodeKV2(&fdmx);
	else
		UnserializeDMX(v_buf,&DmeModelRoot);

	fdmx.close();
	
	if (!DmeModelRoot)
	{
		FatalErr("DMX decoding failed");
		return 1;
	}

	CDmxElement* model = DmeModelRoot->GetValue<CDmxElement*>("model");
	if (model)
		WriteModel( model, version );
	else
	{
		CDmxElement* animationList = DmeModelRoot->GetValue<CDmxElement*>("animationList");
		if (animationList) {
			const CUtlVector<CDmxElement*>* animations = &animationList->GetArray<CDmxElement*>("animations");
			if (animations)
				for (int i=0; i < animations->Count(); i++ )
					WriteAnimation(animations->Element(i),version);
		}
		else
			Error("Nothing to export in DMX");
	}

	EndDMXContext(true);
	CloseHandle(StdOut);
	CloseHandle(StdErr);
	return 0;
}