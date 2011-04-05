#include "stdafx.h"

enum contexts_t
{
	NONE,
	ELEMENT,
	ARRAY,
	END
} contexts;

CDmxElement* DecodeElement(const char* in_type);

char* curLine;
CDmxElement* curElem = DmeModelRoot;
ifstream* g_file;

contexts_t ParseLine(char* line,CUtlStringList& words)
{
	contexts_t retVal = NONE;
	unsigned int LineLen = strlen(curLine)+1;

	char* curWord = new char[LineLen];
	memset(curWord,0,LineLen);
	
	bool InQuote = false;
	
	for (unsigned int i=0; i < strlen(curLine); i++)
	{
		char cur = curLine[i];
		if (
			( !InQuote && (cur == ' ' || cur == '\t') && strlen(curWord) )
			||
			(  InQuote &&  cur == '"' )
			)
		{
			// end of word
			unsigned int WordLen = strlen(curWord)+1;
			char* WholeWord = new char[WordLen];
			memcpy(WholeWord,curWord,WordLen);
			words.AddToTail(WholeWord);
			memset(curWord,0,LineLen);
			InQuote = false;
		}
		else 
		{
			switch(cur)
			{
			case '}':
			case ']':
				retVal = END;
				break;
			case '{':
				retVal = ELEMENT;
				break;
			case '[':
				retVal = ARRAY;
				break;
			case '"':
				InQuote = true;
				break;
			case ' ':
			case '\t':
				if (!InQuote)
					continue;
			default:
				curWord[strlen(curWord)] = cur; // store the character
			}
		}
	}
	delete[] curWord;
	return retVal;
}

DmAttributeType_t GetKV2Type(const char* TypeString)
{
	int len = strlen(TypeString);
	char* MangledType = new char[len+1];
	MangledType[len] = 0;
	memcpy(MangledType,TypeString,len);
	char* Underscore = strstr(MangledType,"_");
	if (Underscore)
		*Underscore = '\0'; // don't care if it's an array or not

	DmAttributeType_t Type = AT_UNKNOWN;

	if ( strcmp(MangledType,"int") == 0)
		Type = AT_INT;
	else if ( strcmp(MangledType,"float") == 0)
		Type = AT_FLOAT;
	else if ( strcmp(MangledType,"bool") == 0)
		Type = AT_BOOL;
	else if ( strcmp(MangledType,"color") == 0)
		Type = AT_COLOR;
	else if ( strcmp(MangledType,"vector2") == 0)
		Type = AT_VECTOR2;
	else if ( strcmp(MangledType,"vector3") == 0)
		Type = AT_VECTOR3;
	else if ( strcmp(MangledType,"vector4") == 0)
		Type = AT_VECTOR4;
	else if ( strcmp(MangledType,"quaternion") == 0)
		Type = AT_QUATERNION;
	else if ( strcmp(MangledType,"qangle") == 0)
		Type = AT_QANGLE;
	else if ( strcmp(MangledType,"quaternion") == 0)
		Type = AT_QUATERNION;
	else if ( strcmp(MangledType,"matrix") == 0)
		Type = AT_VMATRIX;
	else if ( strcmp(MangledType,"string") == 0)
		Type = AT_STRING;
	else if ( strcmp(MangledType,"binary") == 0)
		Type = AT_VOID;
	else if ( strcmp(MangledType,"time") == 0)
		Type = AT_TIME;
	else if ( strcmp(MangledType,"element") == 0)
		Type = AT_ELEMENT;

	delete[] MangledType;
	return Type;
}

void* GetKV2Attribute(const CUtlStringList* words, int& bytes_out, DmAttributeType_t type = AT_UNKNOWN)
{
	bool IsArray = type != AT_UNKNOWN;
	void* retVal = 0;
	char* value = 0;

	if (IsArray)
	{
		value = words->Element(0);
	}
	else
	{
		assert(words->Count() == 3);
		type = GetKV2Type(words->Element(1));
		value = words->Element(2);
	}

	CUtlStringList ValueWords;
	ParseLine(value,ValueWords);

	DWORD fval;
	Color colVal;
	Vector4D vecVal;
	VMatrix matVal;

	switch (type)
	{
	case AT_INT:
		retVal = (void*)atoi(value);
		bytes_out = sizeof(int);
		break;
	case AT_FLOAT:
		fval = atof(value); // can't cast directly to void
		retVal = (void*)fval;
		bytes_out = sizeof(float);
		break;
	case AT_BOOL:
		retVal = (void*)strcmp(value,"false");
		bytes_out = sizeof(bool);
		break;
	case AT_COLOR:
		for (int i=0;i<3;i++)
			colVal[i] = atoi(ValueWords.Element(i));
		retVal = (void*)&colVal;
		bytes_out = sizeof(bool);
		break;
	case AT_VECTOR2:
		for (int i=0;i<2;i++)
			vecVal[i] = atof(ValueWords.Element(i));
		retVal = (void*)&vecVal;
		bytes_out = sizeof(Vector2D);
		break;
	case AT_VECTOR3:
	case AT_QANGLE:
		for (int i=0;i<3;i++)
			vecVal[i] = atof(ValueWords.Element(i));
		retVal = (void*)&vecVal;
		bytes_out = sizeof(Vector);
		break;
	case AT_VECTOR4:
	case AT_QUATERNION: // might change someday?
		for (int i=0;i<4;i++)
			vecVal[i] = atof(ValueWords.Element(i));
		retVal = (void*)&vecVal;
		bytes_out = sizeof(Vector4D);
		break;
	case AT_VMATRIX:
		for (int i=0;i<4;i++)
			for (int j=0;j<4;j++)
				matVal.m[i][j] = atof(ValueWords.Element(i));
		retVal = (void*)&matVal;
		bytes_out = sizeof(VMatrix);
		break;
	case AT_STRING:
		retVal = value;
		bytes_out = strlen(value) + 1;
		break;
	case AT_VOID:
		retVal = value;
		bytes_out = strlen(value);
		break;
	case AT_ELEMENT:
		retVal = DecodeElement(ValueWords.Element(0));
		bytes_out = sizeof(CDmxElement);
		break;
	}

	return memcpy(MemAlloc_Alloc(bytes_out),retVal,bytes_out); // leak!!
}

CDmxElement* DecodeElement(const char* in_type)
{
	CDmxElement* curElem = CreateDmxElement(in_type);
	CDmxAttribute* curAttr;
	
	while (strlen(curLine))
	{
		CUtlStringList words;
		ParseLine(curLine,words);
		
		if (words.Count())
		{
			for (int i=0; i<words.Count();i++)
				Msg("%s ",words.Element(i));
			Msg("\n");

			char *name=0,*value=0;
			DmAttributeType_t type;

			if (words.Count() == 3)
			{
				curAttr = curElem->AddAttribute(words.Element(0));
				type = GetKV2Type(words.Element(1));
			}
			
			if (words.Count() < 3)
			{
				CUtlStringList ValueWords;
				g_file->getline(curLine,512);
				contexts_t opener = ParseLine(curLine,ValueWords);
				ValueWords.RemoveAll();
					
				CUtlVector<void*> values;
				CUtlVector<int> test;
				switch( opener )
				{
				case ARRAY:
					curAttr = curElem->AddAttribute(words.Element(0));
					curAttr->GetArrayForEdit<int>();
					
					type = GetKV2Type(words.Element(1));
					int size = 0;
					g_file->getline(curLine,512);					
					while (ParseLine(curLine,ValueWords) != END && strlen(curLine))
					{
						values.AddToTail(GetKV2Attribute(&ValueWords,size,type));
						g_file->getline(curLine,512);
					}
					break;
				case ELEMENT:
					if(words.Count() == 2)
						curElem->AddAttribute(words.Element(0))->SetValue(DecodeElement(words.Element(1)));
					else
						curElem = CreateDmxElement(words.Element(0));
					break;
				default:
					FatalErr("Invalid Keyvalues2 file");
					break;
				}

			}

			/*name = words[0];
			if (words.Count() == 1)
			{
				curAttr->SetValue(DecodeElement(name));
				continue;
			}
			type =  words[1];
			value = words[2];

			curAttr = curElem->AddAttribute(name);

			Msg("%s\n",name);

			if (strcmp(type,"elementid") == 0)
				continue; //curAttr->SetValue<CDmxElement*>(0);
			else if (strcmp(type,"string") == 0)
				curAttr->SetValue<CUtlString>(value);
			else if (strcmp(type,"bool") == 0)
				curAttr->SetValue<bool>(value[0] == 1);
			else if (strcmp(type,"float") == 0)
				curAttr->SetValue<float>(atof(value));
			else if (strcmp(type,"int") == 0)
				curAttr->SetValue<int>(atoi(value));*/
		}
		g_file->getline(curLine,512);
	}

	return curElem;
}

void DecodeKV2(ifstream* file)
{
	g_file = file;
	curLine = new char[512];
	file->seekg(0);
	file->getline(curLine,512);
	while (strlen(curLine))
	{
		if (curLine[0] != '<')
		{
			if (!DmeModelRoot)
				DmeModelRoot = DecodeElement("DmElement");
		}
		file->getline(curLine,512);
	}
	delete[] curLine;
}