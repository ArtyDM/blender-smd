#pragma once

#define NULL 0

#ifdef DMX_MODEL_EXPORTS
#define DMX_MODEL_API __declspec(dllexport)
#else
#define DMX_MODEL_API __declspec(dllimport)
#endif

#include "dmxloader/dmxloader.h"
#include "dmxloader/dmxelement.h"
#include "dmxloader/dmxattribute.h"

#include "tier1/utlbuffer.h"
#include "tier1/utlvector.h"

#include "targetver.h"
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

using namespace std;
#include <fstream>

extern CDmxElement* DmeModelRoot;

static HANDLE StdOut = GetStdHandle(STD_OUTPUT_HANDLE);
static HANDLE StdErr = GetStdHandle(STD_ERROR_HANDLE);
static DWORD written;

static int modl_v = 1;
void DecodeKV2(ifstream* file);

#define Output(buf, bytes) WriteFile(StdOut,buf,bytes,&written,0);
#define OutputInt(buf) Output(&buf,sizeof(int))
#define OutputFloat(buf) Output(&buf,sizeof(float))
#define OutputBool(b) Output(b ? "\1" : "\0",1)
#define OutputStr(buf) WriteFile(StdOut,buf,strlen(buf),&written,0);

#define Error(buf) WriteFile(StdErr,buf,strlen(buf),&written,0);
void FatalErr(const char* msg);

void WriteModel(CDmxElement* DmeModel,int version);
void WriteAnimation(CDmxElement* DmeModel,int version);