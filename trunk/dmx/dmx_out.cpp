#include "stdafx.h"

CDmxElement* FindChild(CDmxElement* Dme, const char* name, CDmxElement* transform)
{
	Dme->GetName();
	const CUtlVector<CDmxElement*>* children = &Dme->GetArray<CDmxElement*>("children");
	for (int i=0; i < children->Count(); i++)
	{
		CDmxElement* pCur = children->Element(i);
		if (
			(name && strcmp( pCur->GetValueString("name"), name) == 0)
			|| ( transform && pCur->GetValue<CDmxElement*>("transform") == transform)
			)
			return pCur;
		else
		{
			CDmxElement* res = FindChild(pCur,name,transform);
			if (res) return res;
		}
	}
	return 0;
}

CDmxElement* FindChild(CDmxElement* Dme,CDmxElement* transform)
{
	return FindChild(Dme,0,transform);
}
CDmxElement* FindChild(CDmxElement* Dme,const char* name)
{
	return FindChild(Dme,name,0);
}

CUtlVector<CDmxElement*>* jointList_new = 0;
const CUtlVector<CDmxElement*>* GetJointList()
{
	if (jointList_new)
		return jointList_new;

	CDmxElement* skeleton = DmeModelRoot->GetValue<CDmxElement*>("skeleton");
	if (!skeleton)
		FatalErr("Could not find skeleton");
	const CUtlVector<CDmxElement*>* jointList = &skeleton->GetArray<CDmxElement*>("jointList");
	if (jointList->Count())
		return jointList;
		
	jointList_new = new CUtlVector<CDmxElement*>;
	const CUtlVector<CDmxElement*>* children = &skeleton->GetArray<CDmxElement*>("children");
	const CUtlVector<CDmxElement*>* TransformList = &skeleton->GetArray<CDmxElement*>("baseStates").Element(0)->GetArray<CDmxElement*>("transforms");

	for (int i=0; i< TransformList->Count(); i++)
	{
		CDmxElement* pCur = FindChild(skeleton,TransformList->Element(i)->GetName());
		if (pCur)
			jointList_new->AddToTail(pCur);
	}
	return jointList_new;
	
}

void WriteName(CDmxElement* Dme)
{
	int NameLen = strlen(Dme->GetName());
	OutputInt(NameLen);
	Output(Dme->GetName(),NameLen);
}

void WriteHeader(CDmxElement* Dme)
{	
	OutputStr("MODL");
	OutputInt(modl_v);
	WriteName(Dme);
}

void WriteTransform(CDmxElement* DmeTransform)
{
	if (!DmeTransform)
		return;

	assert(strcmp(DmeTransform->GetTypeString(),"DmeTransform") == 0);

	OutputStr("TRFM");
	Output(&DmeTransform->GetValue<Vector>("position"),sizeof(Vector));
	Output(&DmeTransform->GetValue<Quaternion>("orientation"),sizeof(Quaternion));
}

void WriteAttachment(CDmxElement* DmeDag)
{
	assert(strcmp(DmeDag->GetTypeString(),"DmeDag") == 0);

	CDmxElement* DmeAttachment = DmeDag->GetValue<CDmxElement*>("shape");
	if (!DmeAttachment)
		return;

	OutputStr("ATCH");
	WriteName(DmeAttachment);
	OutputBool(DmeAttachment->GetValue<bool>("isRigid"));
	OutputBool(DmeAttachment->GetValue<bool>("isWorldAligned"));
	WriteTransform(DmeDag->GetValue<CDmxElement*>("transform"));
}

void WriteBone(CDmxElement* DmeJoint,bool ListOnly = false)
{
	assert(strcmp(DmeJoint->GetTypeString(),"DmeJoint") == 0);

	static const CUtlVector<CDmxElement*>* TransformList = &DmeModelRoot->GetValue<CDmxElement*>("skeleton")->GetArray<CDmxElement*>("baseStates").Element(0)->GetArray<CDmxElement*>("transforms");

	/*static const CUtlVector<CDmxElement*>* jointTransforms = &DmeModelRoot->GetValue<CDmxElement*>("skeleton")->GetArray<CDmxElement*>("jointTransforms");
	if (!jointTransforms) {
		FatalErr("Invalid DMX: Skeleton but no jointTransforms");
	}*/

	if ( DmeJoint->HasAttribute("written") )
		return;
	DmeJoint->AddAttribute("written");

	OutputStr("BONE");
	WriteName(DmeJoint);
	int ID = GetJointList()->Find(DmeJoint);
	OutputInt(ID);
	
	if (!ListOnly)
		WriteTransform(DmeJoint->GetValue<CDmxElement*>("transform"));

	const CUtlVector<CDmxElement*>* children = &DmeJoint->GetArray<CDmxElement*>("children");
	int NumChildren = children->Count();
	if (NumChildren)
	{
		for (int i=0; i < NumChildren; i++ )
		{
			CDmxElement* pCur = children->Element(i);
			if (
					strcmp(pCur->GetTypeString(), "DmeJoint") == 0
					||
					(
						strcmp(pCur->GetTypeString(), "DmeDag") == 0
						&&
						pCur->GetValue<CDmxElement*>("shape")
					)
				)
				continue;
			else
				DmeJoint->GetAttribute("children")->GetArrayForEdit<CDmxElement*>().Remove(i); // not something we want to export
		}
		NumChildren = children->Count();
		if (NumChildren)
		{
			OutputStr("CHDN");
			OutputInt(NumChildren);
			for (int i=0; i < NumChildren; i++ )
			{
				CDmxElement* pCur = children->Element(i);
				if ( strcmp(pCur->GetTypeString(), "DmeDag") == 0) {
					if (!ListOnly)
						WriteAttachment(pCur);
				}
				else
					WriteBone(pCur,ListOnly);
			}
		}
	}
}

void WriteMesh(CDmxElement* DmeMesh, int version)
{	
	assert(
		strcmp(DmeMesh->GetTypeString(),"DmeDag") == 0 ||
		strcmp(DmeMesh->GetTypeString(),"DmeMesh") == 0
		);

	CDmxElement* shape = DmeMesh->GetValue<CDmxElement*>("shape");

	if (shape)
	{
		if ( strcmp(shape->GetTypeString(),"DmeMesh") == 0 )
		{
			CDmxElement* DmeMesh = shape;
			CDmxElement* DmeVertexData = DmeMesh->GetValue<CDmxElement*>("currentState");
		
			OutputStr("MESH");
			WriteName(DmeMesh);
			WriteTransform(DmeMesh->GetValue<CDmxElement*>("transform"));
	
			OutputStr("VERT");
			const CUtlVector<Vector>* pos		= &DmeVertexData->GetArray<Vector>("positions");
			const CUtlVector<int>* PosIndices	= &DmeVertexData->GetArray<int>("positionsIndices");
			int verts							= PosIndices->Count();

			OutputInt(verts);
			for ( int i = 0; i < verts; i++)
				Output(&pos->Element( PosIndices->Element(i) ),sizeof(Vector));

			OutputStr("NORM");
			const CUtlVector<Vector>* norms		= &DmeVertexData->GetArray<Vector>("normals");
			const CUtlVector<int>* normIndices	= &DmeVertexData->GetArray<int>("normalsIndices");
			for ( int i = 0; i < verts; i++)
				Output(&norms->Element( normIndices->Element(i) ),sizeof(Vector));

	
			const CUtlVector<CDmxElement*>* FaceSets = &DmeMesh->GetArray<CDmxElement*>("faceSets");
			for( int i=0; i < FaceSets->Count(); i++)
			{
				CDmxElement* CurSet = FaceSets->Element(i);
				OutputStr("FACE");
		
				CUtlString mtlName = CurSet->GetValue<CDmxElement*>("material")->GetValue<CUtlString>("mtlName");
				int mtlNameLen = mtlName.Length();
				OutputInt(mtlNameLen);
				Output(mtlName.Get(),mtlNameLen);

				const CUtlVector<int>* faces = &CurSet->GetArray<int>("faces");
				int FacesSize = faces->Count();
				OutputInt(FacesSize);
				Output(faces->Base(),sizeof(int) * FacesSize);
			}

			OutputStr("TEXC");
			const CUtlVector<Vector2D>* uvs		= &DmeVertexData->GetArray<Vector2D>("textureCoordinates");
			const CUtlVector<int>* uvIndices	= &DmeVertexData->GetArray<int>("textureCoordinatesIndices");

			for ( int i = 0; i < verts; i++)
			{
				Output(&uvs->Element( uvIndices->Element(i) ),sizeof(Vector2D));
			}
						
			int NumWeightedBones = DmeVertexData->GetValue<int>("jointCount");
			if ( NumWeightedBones )
			{
				OutputStr("WMAP");
				OutputInt(NumWeightedBones);
				const CUtlVector<float>* weights	= &DmeVertexData->GetArray<float>("jointWeights");
				const CUtlVector<int>* wtIndices	= &DmeVertexData->GetArray<int>("jointIndices");
				
				for ( int i=0; i < verts; i++)
				{
					int cur = PosIndices->Element(i) * NumWeightedBones;
					
					for ( int j=0; j < NumWeightedBones; j++)
					{
						OutputFloat(weights->Element(cur));
						OutputInt(wtIndices->Element(cur));
						cur++;
					}
				}
			}
		}
		
		else if ( strcmp(shape->GetTypeString(),"DmeAttachment") == 0 )
		{
			WriteAttachment(DmeMesh);
		}
		else
		{
			AssertMsg(0,shape->GetTypeString());
		}
	}

	const CUtlVector<CDmxElement*>* children = &DmeMesh->GetArray<CDmxElement*>("children");
	int NumChildren = children->Count();
	if (NumChildren)
	{
		OutputStr("CHDN");
		OutputInt(NumChildren);
		for ( int i=0; i < NumChildren; i++)
			WriteMesh(children->Element(i),version);
	}
}

const CUtlVector<CDmxElement*>* WriteSkeleton(CDmxElement* DmeModel, int version, bool ListOnly = false)
{
	const CUtlVector<CDmxElement*>* children = &DmeModel->GetArray<CDmxElement*>("children");
	bool HadBones = false;
	
	for ( int i = 0; i < children->Count(); i++ )
	{
		if ( strcmp(children->Element(i)->GetTypeString(),"DmeJoint") == 0 )
		{
			if (!HadBones)
			{
				OutputStr("SKEL");
				HadBones = true;
			}
			WriteBone(children->Element(i),ListOnly);
		}
	}
	if (HadBones)
		return GetJointList();

	return 0;
}

void WriteModel(CDmxElement* DmeModel, int version)
{
	WriteHeader(DmeModel);

	CDmxElement* transform = DmeModel->GetValue<CDmxElement*>("transform");
	WriteTransform(transform);

	WriteSkeleton(DmeModel,version);
	
	const CUtlVector<CDmxElement*>* children = &DmeModel->GetArray<CDmxElement*>("children");
	if (children)
		for ( int i = 0; i < children->Count(); i++)
		{
			CDmxElement* pCur = children->Element(i);
			if ( strcmp(pCur->GetTypeString(), "DmeDag") == 0 || strcmp(pCur->GetTypeString(), "DmeMesh") == 0 )
				WriteMesh(pCur,version);
		}
}

void WriteAnimation(CDmxElement* anim, int version)
{	
	CDmxElement* skeleton = DmeModelRoot->GetValue<CDmxElement*>("skeleton");
	if (!skeleton) {
		FatalErr("Invalid DMX: Animation without skeleton\n");
	}

	WriteHeader(anim);

	const CUtlVector<CDmxElement*>* jointList = WriteSkeleton(skeleton,version,true);

	if (!jointList)
	{
		char buf[64];
		if (version <= 18)
			sprintf_s(buf,"Invalid DMX: could not find skeleton\n");
		else
			sprintf_s(buf,"Animation unsupported for DMX version %i\n",version);
		FatalErr(buf);
	}

	OutputStr("ANIM");
	//const char* text = anim->GetValue<CUtlString>("text").Get(); // no idea what this value is actually for...it's not the name
	//Output(text,strlen(text));
	
	CDmxElement* timeFrame = anim->GetValue<CDmxElement*>("timeFrame");

	float FPS = anim->GetValue<int>("frameRate");
	float finalFPS = FPS * timeFrame->GetValue<float>("scale");
	OutputFloat(finalFPS);
	
	float duration;
	switch (version)
	{
	case 0:
	case 1:
		duration = (float)timeFrame->GetValue<int>("durationTime") / 10000; // yes 10,000
		break;
	default:
		duration = timeFrame->GetValue<DmeTime_t>("duration").GetSeconds();
		break;
	}
	OutputFloat(duration);
	
	const CUtlVector<CDmxElement*>* channels = &anim->GetArray<CDmxElement*>("channels");
	if (channels)
		for (int i=0; i < channels->Count(); i++) {
			CDmxElement* channel = channels->Element(i);

			const char* toAttribute = channel->GetValue<CUtlString>("toAttribute");
			char Type;
			if ( strcmp(toAttribute,"position") == 0 )
				Type = 'p';
			else if ( strcmp(toAttribute,"orientation") == 0 )
				Type = 'o';
			else
				continue;

			CDmxElement* toElement = channel->GetValue<CDmxElement*>("toElement");
			if (!toElement || !FindChild(skeleton,toElement) || strcmp(FindChild(skeleton,toElement)->GetTypeString(),"DmeJoint") != 0)
				continue;
			const char* name = FindChild(skeleton,toElement)->GetName();

			// bone ID
			int BoneID = -1;
			for (int j=0; j < jointList->Count(); j++) {
				 CDmxElement* curTransform = jointList->Element(j)->GetValue<CDmxElement*>("transform");
				 jointList->Element(j)->GetName();
				 if (curTransform == toElement && strcmp( jointList->Element(j)->GetTypeString(), "DmeJoint") == 0)
				 {					
					BoneID = j;
					break;
				 }
			}
			if (BoneID == -1)
				continue;
			
			OutputStr("CHAN");
			Output(&Type,1); // 'p' or 'o'
			OutputInt(BoneID);

			// Num layers
			const CUtlVector<CDmxElement*>* layers = &channel->GetValue<CDmxElement*>("log")->GetArray<CDmxElement*>("layers");
			int numLayers = layers->Count();
			OutputInt(numLayers);

			for (int j=0; j < numLayers; j++) {
				CDmxElement* layer = layers->Element(j);				
				OutputStr("L");

				const CUtlVector<DmeTime_t>* times_t = 0;
				const CUtlVector<int>* times_int = 0;
				if (version <= 1)
					times_int = &layer->GetArray<int>("times");
				else
					times_t = &layer->GetArray<DmeTime_t>("times");

				const CUtlVector<Vector>* Pvalues = 0;
				const CUtlVector<Quaternion>* Ovalues = 0;
				switch(Type) {
				case 'p':
					Pvalues = &layer->GetArray<Vector>("values");
					break;
				case 'o':
					Ovalues = &layer->GetArray<Quaternion>("values");
					break;
				}

				int Frames;
				if (times_t)
					Frames = times_t->Count();
				else
					Frames = times_int->Count();
				OutputInt(Frames);

				for (int f=0; f < Frames; f++) {
					float time;
					if (times_t)
						time = times_t->Element(f).GetSeconds();
					else
						time = (float)times_int->Element(f) / 10000; // yes 10,000
					OutputFloat(time);

					switch(Type) {
					case 'p':
						Output(&Pvalues->Element(f),sizeof(Vector));
						break;
					case 'o':
						Output(&Ovalues->Element(f),sizeof(Quaternion));
						break;
					}
				}
			}
		}
}