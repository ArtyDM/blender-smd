#include "stdafx.h"

enum contexts_t
{
	NONE,
	ELEMENT,
	ARRAY
};

void DecodeKV2(ifstream* file)
{
	contexts_t context = NONE;
	int level = 0;
	CDmxElement* curElem = DmeModelRoot;
	CDmxAttribute* curAttr = 0;

	char* curLine = new char[512];
	file->seekg(0);
	file->getline(curLine,512);
	while (strlen(curLine))
	{
		if (curLine[0] != '<')
		{
			CUtlVector<char*> words;
			unsigned int LineLen = strlen(curLine)+1;
			char* curWord = new char[LineLen];
			memset(curWord,0,LineLen);
			bool InQuote = false;
			for (unsigned int i=0; i < strlen(curLine); i++)
			{
				char cur = curLine[i];
				if ( ( !InQuote && (cur == ' ' || cur == '\t') && strlen(curWord) ) ||
					 (  InQuote &&  cur == '"' )
					 )
				{
					unsigned int WordLen = strlen(curWord)+1;
					char* FinalWord = new char[WordLen];
					memcpy(FinalWord,curWord,WordLen);
					words.AddToTail(FinalWord);
					Msg("%s\n",words.Tail());
					memset(curWord,0,LineLen);
					InQuote = false;
				}
				else if ( cur == '{' )
				{
					context = ELEMENT;
					level++;
				}
				else if ( cur == '}' )
				{					
					level--;
					if (level == 0)
						context = NONE;
				}
				else if ( cur == '[' )
					context = ARRAY;
				else if ( cur == ']' )
					context = ELEMENT;
				else if ( cur == '"' )
					InQuote = true;
				else if (cur == ' ' || cur == '\t')
					continue;
				else
					curWord[strlen(curWord)] = cur;
					curWord[strlen(curWord)] = 0;
			}
			delete[] curWord;

			if (words.Count())
				switch(context)
				{
				case NONE:
					curElem = CreateDmxElement(words[0]);
					
					break;
				case ELEMENT:
					char *name,*type,*value;
					name =  words[0];
					type =  words[1];
					value = words[2];

					curAttr = curElem->AddAttribute(name);

					if (strcmp(type,"elementid") == 0)
						curAttr->SetValue<CDmxElement*>(0);
					else if (strcmp(type,"string") == 0)
						curAttr->SetValue(value);
					else if (strcmp(type,"bool") == 0)
						curAttr->SetValue<bool>(value[0] == 1);
					else if (strcmp(type,"float") == 0)
						curAttr->SetValue<float>(atof(value));
					else if (strcmp(type,"float_array") == 0) {
						0;//curAttr->SetValue<CUtlVector<float>>(0);
					}
					else if (strcmp(type,"int") == 0)
						curAttr->SetValue<int>(atoi(value));

					break;
				case ARRAY:
					break;
				}
		}
		file->getline(curLine,512);
	}
	delete[] curLine;
}