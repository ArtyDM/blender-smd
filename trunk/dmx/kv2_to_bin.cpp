#include "stdafx.h"

enum contexts_t
{
	NONE,
	HEADER,
	VALUE,
	ELEMENT,
	ARRAY,
	END_ARRAY,
	END_ELEMENT,
	END_FILE
} contexts;

struct WantLink
{
	WantLink(CDmxAttribute* Attr, int index = -1)
	{
		m_Attr = Attr;
		m_Index = index;
	}

	CDmxAttribute* m_Attr;
	int m_Index;
};

struct ElementIDLink
{
	char m_ID[37];
	CDmxElement* m_Target;
	CUtlVector<WantLink>* WantLinks;

	ElementIDLink(const char* ID)
	{
		WantLinks = new CUtlVector<WantLink>;
		memcpy(m_ID,ID,36);
		m_ID[36] = 0;
		m_Target = 0;
	}

	bool operator==(const char* szOther)
	{
		return ( strcmp(m_ID,szOther) == 0);
	}
};

CUtlVector<ElementIDLink> ElementIDs;

ElementIDLink* GetElementIDLink(const char* name)
{
	for (int i=0;i<ElementIDs.Count();i++)
	{
		if (ElementIDs.Element(i) == name)
			return &ElementIDs.Element(i);
	}
	return 0;
}

CDmxElement* DecodeElement(CDmxAttribute* Attr, const char* in_type, bool Array = false);

ifstream* g_file;

contexts_t ParseLine(CUtlStringList* words)
{
	if (g_file->eof())
		return END_FILE;

	contexts_t retVal = NONE;

	char curLine[512];
	g_file->getline(curLine,512);
	unsigned int LineLen = strlen(curLine)+1;

	if (curLine[0] == '<')
		return HEADER;

	words->RemoveAll();

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
			words->AddToTail(WholeWord);
			retVal = VALUE;
			memset(curWord,0,LineLen);
			InQuote = false;
		}
		else 
		{
			switch(cur)
			{
			case '}':
				retVal = END_ELEMENT;
				break;
			case ']':
				retVal = END_ARRAY;
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
		*Underscore = 0; // don't care if it's an array or not

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
	else if (
			strcmp(MangledType,"element") == 0
			||
			strcmp(MangledType,"elementid") == 0
			)
		Type = AT_ELEMENT;

	delete[] MangledType;
	return Type;
}

namespace Decoders
{
void DecodeInt(CDmxAttribute* Attr,const CUtlStringList* words)
{
	if (words->Count() == 3)
		Attr->SetValue<int>(atoi(words->Element(2)));
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<int>().AddToTail( atoi(array_words.Element(0)) );
	}
}

void DecodeFloat(CDmxAttribute* Attr,const CUtlStringList* words)
{		
	if (words->Count() == 3)	
		Attr->SetValue<float>(atof(words->Element(2)));
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<float>().AddToTail( atof(array_words.Element(0)));
	}
}

void DecodeBool(CDmxAttribute* Attr,const CUtlStringList* words) // integer bool
{
	if (words->Count() == 3)	
		Attr->SetValue<bool>( atoi(words->Element(2)) != 0 );
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<bool>().AddToTail( atoi(array_words.Element(0)) != 0 );
	}
}

Color DecodeColor(char* value)
{
	Color res;
	char* c = value;
	int i = 0;
	while (*c && *c != '"')
	{
		if (*c == ' ')
		{
			*c = 0;
			res[i] = atoi(value);
			value = c + 1;
			i++;
		}
		c++;
	}
	return res;
}

void DecodeColor(CDmxAttribute* Attr,const CUtlStringList* words)
{
	if (words->Count() == 3)	
		Attr->SetValue<Color>(DecodeColor(words->Element(2)));
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<Color>().AddToTail( DecodeColor(array_words.Element(0)) );
	}
}

template <typename T>
T DecodeFloats_internal(char* value)
{
	T res;
	char* c = value;
	int i = 0;
	while (*c)
	{
		switch(*c)
		{
		case ' ':
			if (*c == ' ')
			{
				*c = 0;
				res[i] = atof(value);
				value = c + 1;
				i++;
			}
		}
		c++;
	}
	res[i] = atof(value); // catch the last one
	return res;
}

template <typename T>
void DecodeFloats(CDmxAttribute* Attr,const CUtlStringList* words)
{
	if (words->Count() == 3)	
		Attr->SetValue<T>(DecodeFloats_internal<T>(words->Element(2)));
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<T>().AddToTail( DecodeFloats_internal<T>(array_words.Element(0)) );
	}
}

void DecodeString(CDmxAttribute* Attr,const CUtlStringList* words)
{
	if (words->Count() == 3)	
		Attr->SetValue(words->Element(2));
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<CUtlString>().AddToTail( array_words.Element(0) );
	}
}

void DecodeBinary(CDmxAttribute* Attr,const CUtlStringList* words)
{
	if (words->Count() == 3)	
		Attr->SetValue<CUtlBinaryBlock>( CUtlBinaryBlock( words->Element(2),strlen(words->Element(2)) ) ); // is b0 allowed??
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<CUtlBinaryBlock>().AddToTail( CUtlBinaryBlock( words->Element(2),strlen(words->Element(2)) ) );
	}
}

void DecodeTime(CDmxAttribute* Attr,const CUtlStringList* words)
{
	if (words->Count() == 3)	
		Attr->SetValue<DmeTime_t>( DmeTime_t(atof(words->Element(2))) );
	else
	{
		CUtlStringList array_words;
		if (ParseLine(&array_words) == ARRAY)
			while ( ParseLine(&array_words) == VALUE)
				Attr->GetArrayForEdit<DmeTime_t>().AddToTail( DmeTime_t(atof(words->Element(2))) );
	}
}

}

void HandleElementIDValue(const char* ID, CDmxAttribute* Attr,int index = -1)
{
	ElementIDLink* IDL = GetElementIDLink(ID);
	if (!IDL)
	{
		ElementIDs.AddToTail( ElementIDLink(ID) );
		IDL = &ElementIDs.Tail();
	}
	if (IDL->m_Target)
	{
		Attr->SetValue<CDmxElement*>(IDL->m_Target);
	}
	else
	{
		IDL->WantLinks->AddToTail(WantLink(Attr,index));
	}
}

void DecodeAttribute(CDmxElement* Dme,CUtlStringList* AttrWords)
{
	DmAttributeType_t type = GetKV2Type(AttrWords->Element(1));

	if (type == AT_UNKNOWN && AttrWords->Count() == 2)
		type = AT_ELEMENT;
	
	CDmxAttribute* Attr = Dme->AddAttribute(AttrWords->Element(0));

	using namespace Decoders;
	switch(type)
	{
	case AT_INT:
		DecodeInt(Attr,AttrWords);
		break;
	case AT_FLOAT:
		DecodeFloat(Attr,AttrWords);
		break;
	case AT_BOOL:
		DecodeBool(Attr,AttrWords);
		break;
	case AT_COLOR:
		DecodeColor(Attr,AttrWords);
		break;
	case AT_VECTOR2:
		DecodeFloats<Vector2D>(Attr,AttrWords);
		break;
	case AT_VECTOR3:
		DecodeFloats<Vector>(Attr,AttrWords);
		break;
	case AT_VECTOR4:
		DecodeFloats<Vector4D>(Attr,AttrWords);
		break;
	case AT_QANGLE:
		DecodeFloats<QAngle>(Attr,AttrWords);
		break;
	case AT_QUATERNION:
		DecodeFloats<Quaternion>(Attr,AttrWords);
		break;
	case AT_VMATRIX:
		//DecodeFloats<VMatrix>(Attr,AttrWords);
		break;
	case AT_STRING:
		DecodeString(Attr,AttrWords);
		break;
	case AT_VOID:
		DecodeBinary(Attr,AttrWords); // got a problem with that?
		break;
	case AT_TIME:
		DecodeTime(Attr,AttrWords);
		break;
	case AT_ELEMENT:
		if ( strcmp(AttrWords->Element(1),"element_array") != 0)
		{
			if (AttrWords->Count() == 2)
				DecodeElement(Attr,AttrWords->Element(1));
			else
			{
				if ( strcmp(AttrWords->Element(1),"elementid") == 0 )
				{
					ElementIDLink* IDL = GetElementIDLink(AttrWords->Element(2));
					if (!IDL)
					{
						ElementIDs.AddToTail( ElementIDLink(AttrWords->Element(2)) );
						IDL = &ElementIDs.Tail();
					}
					IDL->m_Target = Dme;
				}
				else if ( strlen(AttrWords->Element(2)) )
				{
					HandleElementIDValue(AttrWords->Element(2),Attr);
				}
			}
		}
		else // array
		{
			CUtlStringList array_words;
			int index = 0;
			if (ParseLine(&array_words) == ARRAY)
				while ( ParseLine(&array_words) == VALUE )
				{
					if (array_words.Count() == 1)
						DecodeElement(Attr,array_words.Element(0),true);
					else if (array_words.Count() == 2)
						HandleElementIDValue(array_words.Element(1),Attr,index);
					index++;
				}
		}
		break;
	}
}

CDmxElement* DecodeElement(CDmxAttribute* Attr, const char* in_type, bool Array)
{
	CDmxElement* curElem = CreateDmxElement(in_type);
	if (Attr)
	{
		if (Array)
			Attr->GetArrayForEdit<CDmxElement*>().AddToTail(curElem);
		else
			Attr->SetValue<CDmxElement*>(curElem);
	}

	CUtlStringList ElemWords;
	while (ParseLine(&ElemWords) < END_ELEMENT)
	{
		if (ElemWords.Count() > 1)
			DecodeAttribute(curElem,&ElemWords);
		else
			continue;
	}

	return curElem;
}

void IterateDmxElement(CDmxElement* DmeModelRoot);

void DecodeKV2(ifstream* file)
{
	g_file = file;
	file->seekg(0);
	CUtlStringList RootWords;
	bool HaveRoot = false;
	while (1)
	{
		CDmxElement* Dme;

		contexts_t ParseResult = ParseLine(&RootWords);
		switch( ParseResult )
		{
		case END_FILE:
			goto stop;
		case HEADER:
			continue;
		case VALUE:
			Dme = DecodeElement(0,RootWords.Element(0));
			if (!HaveRoot)
			{
				DmeModelRoot = Dme;
				HaveRoot = true;
			}
		}
	}
stop:
	
	while (ElementIDs.Count())
	{
		assert( ElementIDs.Head().m_Target );
		//Msg("%s (%s)\n",ElementIDs.Head().m_Target->GetName(),ElementIDs.Head().m_Target->GetTypeString());
		for (int j=0;j<ElementIDs.Head().WantLinks->Count();j++)
		{			
			WantLink* cur = &ElementIDs.Head().WantLinks->Element(j);
			//Msg("\t%s %i\n",cur->m_Attr->GetName(),cur->m_Index);
			if (cur->m_Index != -1)
			{
				CUtlVector<CDmxElement*>* arr = &cur->m_Attr->GetArrayForEdit<CDmxElement*>();
				arr->EnsureCount(cur->m_Index + 1);
				arr->Element(cur->m_Index) = ElementIDs.Head().m_Target;
			}
			else
			{
				cur->m_Attr->SetValue<CDmxElement*>( ElementIDs.Head().m_Target );
				//Msg("%s > %s\n",cur->m_Attr->GetName(),ElementIDs.Head().m_Target->GetName());
			}
			
		}
		ElementIDs.Remove(0);
	}

	/*CUtlBuffer buf;
	SerializeDMX(buf,DmeModelRoot);
	FILE* f = fopen("C:\\Users\\Tom\\Desktop\\test.dmx","w");
	fwrite(buf.Base(),1,buf.TellPut(),f);
	fclose(f);*/
}