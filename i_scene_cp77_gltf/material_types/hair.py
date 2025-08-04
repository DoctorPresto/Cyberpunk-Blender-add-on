from ..main.common import *
from ..jsontool import JSONTool

class Hair:
    def __init__(self, BasePath,image_format, ProjPath):
        self.BasePath = BasePath
        self.ProjPath = ProjPath
        self.image_format = image_format

    def create(self,hair,Mat):

        file = (self.BasePath + hair["HairProfile"] + ".json")
        profile = JSONTool.jsonload(file)
        if profile is not None:
            profile= profile["Data"]["RootChunk"]

            Mat.blend_method = 'HASHED'
            vers = bpy.app.version
            if vers[0] == 4 and vers[1] <= 2:
                Mat.shadow_method = 'HASHED'
            else:
                print('set shadows to hashed how in 4.3?')

            CurMat = Mat.node_tree
            Ns=CurMat.nodes
            sockets=bsdf_socket_names()

            aImg=imageFromRelPath(hair["Strand_Alpha"],DepotPath=self.BasePath, ProjPath=self.ProjPath, image_format=self.image_format)
            aImgNode = create_node(Ns,"ShaderNodeTexImage",  (-300,-150), label="Strand_Alpha", image=aImg)
            CurMat.links.new(aImgNode.outputs[0],CurMat.nodes[loc('Principled BSDF')].inputs['Alpha'])

            CurMat.nodes[loc('Principled BSDF')].inputs[sockets['Specular']].default_value = 0

            gImg=imageFromRelPath(hair["Strand_Gradient"],DepotPath=self.BasePath, ProjPath=self.ProjPath, image_format=self.image_format)
            gImgNode = create_node(Ns,"ShaderNodeTexImage",  (-1100,50), label="Strand_Gradient", image=gImg)

            RootToTip = create_node(Ns,"ShaderNodeValToRGB", (-800,50), label = "GradientEntriesRootToTip")
            RootToTip.color_ramp.elements.remove(RootToTip.color_ramp.elements[0])

            counter = 0
            for Entry in profile["gradientEntriesRootToTip"]:
                if counter == 0:
                    RootToTip.color_ramp.elements[0].position = Entry.get("value",0)
                    colr = Entry["color"]
                    RootToTip.color_ramp.elements[0].color = (float(colr["Red"])/255,float(colr["Green"])/255,float(colr["Blue"])/255,float(1))
                else:
                    element = RootToTip.color_ramp.elements.new(Entry.get("value",0))
                    colr = Entry["color"]
                    element.color =  (float(colr["Red"])/255,float(colr["Green"])/255,float(colr["Blue"])/255,float(1))
                counter = counter + 1

            CurMat.links.new(gImgNode.outputs[0],RootToTip.inputs[0])

            idImg=imageFromRelPath(hair["Strand_ID"],DepotPath=self.BasePath, ProjPath=self.ProjPath, image_format=self.image_format)
            idImgNode = create_node(Ns,"ShaderNodeTexImage",  (-1100,350), label="Strand_ID", image=idImg)

            ID = create_node(Ns,"ShaderNodeValToRGB", (-800,350), label = "GradientEntriesID")

            ID.color_ramp.elements.remove(ID.color_ramp.elements[0])
            counter = 0
            for Entry in profile["gradientEntriesID"]:
                if counter == 0:
                    ID.color_ramp.elements[0].position = Entry.get("value",0)
                    colr = Entry["color"]
                    ID.color_ramp.elements[0].color = (float(colr["Red"])/255,float(colr["Green"])/255,float(colr["Blue"])/255,float(1))
                else:
                    element = ID.color_ramp.elements.new(Entry.get("value",0))
                    colr = Entry["color"]
                    element.color = (float(colr["Red"])/255,float(colr["Green"])/255,float(colr["Blue"])/255,float(1))
                counter = counter + 1

            CurMat.links.new(idImgNode.outputs[0],ID.inputs[0])

            mulNode = create_node(Ns,"ShaderNodeMixRGB", (-400,200), blend_type = 'MULTIPLY')
            mulNode.inputs[0].default_value = 1

            CurMat.links.new(ID.outputs[0],mulNode.inputs[1])
            CurMat.links.new(RootToTip.outputs[0],mulNode.inputs[2])

            gamma0 = create_node(Ns,"ShaderNodeGamma",(-200,200))
            gamma0.inputs[1].default_value = 2.2

            CurMat.links.new(mulNode.outputs[0],gamma0.inputs[0])
            CurMat.links.new(gamma0.outputs[0],CurMat.nodes[loc('Principled BSDF')].inputs['Base Color'])

            nMap = CreateShaderNodeNormalMap(CurMat,self.BasePath + hair["Flow"],-200,-250,'Flow',self.image_format)
            CurMat.links.new(nMap.outputs[0],CurMat.nodes[loc('Principled BSDF')].inputs['Normal'])