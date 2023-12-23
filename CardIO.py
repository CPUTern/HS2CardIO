import binascii
import struct
from io import BytesIO
from PIL import Image

# HS2 人物卡读写包

finders_facetype = ["headId"]
finders_skintype = ["bustWeight"]
finders_righteye = ["whiteColor", "whiteColor"]
finders_righteye_whites = ["whiteColor"]
finders_bodypaint1 = ["sunburnColor", "paintInfo"]
finders_bodypaint1a = ["sunburnColor", "paintInfo", "layoutId"]
finders_bodypaint2 = ["sunburnColor", "paintInfo", "rotation"]
finders_bodypaint2a = ["sunburnColor", "paintInfo", "rotation", "layoutId"]
finders_facepaint1 = ["lipGloss", "paintInfo"]
finders_facepaint1a = ["lipGloss", "paintInfo", "layoutId"]
finders_facepaint2 = ["lipGloss", "paintInfo", "rotation"]
finders_facepaint2a = ["lipGloss", "paintInfo", "rotation", "layoutId"]
finders_favor = ["hAttribute"]

def search(src, pattern, occurrence=0, starthere=0):
    timesfound = 0
    maxFirstCharSlot = len(src) - len(pattern) + 1
    for i in range(starthere, maxFirstCharSlot):
        if src[i] != pattern[0]:  # compare only first byte
            continue

        # found a match on first byte, now try to match rest of the pattern
        for j in range(len(pattern) - 1, 0, -1):
            if src[i + j] != pattern[j]:
                break
            if j == 1:
                if timesfound == occurrence:
                    return i
                else:
                    timesfound += 1
                    continue
    return -1

class Charstat:
    def __init__(self, card, cname, dstyle, pn, ofst=0, ender="", ff=None, sdrname=""):
        self.card = card
        self.displayval = ""
        self.controlname = cname
        self.propName = pn  # name of string to start from when locating the data
        self.datastyle = dstyle
        self.end = ender
        self.offset = ofst
        self.pos = 0
        self.idx = 0
        self.instance = 0
        self.slidername = sdrname
        self.findfirst = ff if ff is not None else []
        
    def GetDatastyle(self):
        return self.datastyle

    def ASCIItoHex(self, value):
        # hex_str = ""
        # for char in value:
        #     hex_str += format(ord(char), 'x')
        # return hex_str
        
        return binascii.hexlify(value.encode()).decode()

    @staticmethod
    def HexToASCII(hex_string):
        try:
            byte_data = bytes.fromhex(hex_string)
            return byte_data.decode('ascii')
        except Exception as ex:
            print(ex.message)
            return ""

    def load_data(self, filebytes):
        starthere = 0
        searchfor = self.propName.encode()

        for find_first in self.findfirst:
            marker = find_first.encode()
            starthere = search(filebytes, marker)
        
        if len(self.end) >= 8 and self.end[:8] == "instance":
            instance_str = self.end[8:]
            self.instance = int(instance_str)
            self.end = ""

        hex_str = ""
        datastyle = self.datastyle

        if datastyle == "dec1byte":
            self.pos = search(filebytes, searchfor, self.instance, starthere) + len(self.propName) + self.offset
            current = filebytes[self.pos:self.pos + 1]
            curstring = current.hex()
            hex_str = str(int(curstring, 16))
            self.displayval = hex_str
            return

        if datastyle in ["fullname", "hex"]:
            self.pos = search(filebytes, searchfor, 0, starthere) + len(self.propName) + self.offset
            oldpos = self.pos
            curstring = ""

            while curstring != self.end.lower():
                current = filebytes[self.pos:self.pos + 1]
                curstring = current.hex()
                if curstring != self.end.lower():
                    hex_str += curstring
                    if datastyle == "dec1byte":
                        hex_str = str(int(hex_str, 16))
                        self.displayval = hex_str
                        break
                    self.pos += 1
                else:
                    if datastyle == "fullname":
                        hex_str = self.HexToASCII(hex_str)
                    self.displayval = hex_str
                    break

            self.pos = oldpos

        elif datastyle == "color":
            idx = int(self.end)
            self.pos = search(filebytes, searchfor, 0, starthere) + len(self.propName) + self.offset + 1 + (idx * 5)
            hex_num = filebytes[self.pos:self.pos + 4]
            hex_str = hex_num.hex()
            int_rep = int(hex_str, 16)
            f = int_rep.to_bytes(4, 'little')
            gameval = int.from_bytes(f, 'big') / 255 if idx < 3 else int.from_bytes(f, 'big') / 100
            self.displayval = str(gameval)

        elif datastyle == "normal":
            self.pos = search(filebytes, searchfor, self.instance, starthere) + len(self.propName) + self.offset + 1 
            hex_num = filebytes[self.pos: self.pos + 4]    #bytes中获取hex
            hex_str = hex_num.hex()     #转16进制
            int_rep = int(hex_str, 16)      #转10进制
            f = struct.unpack('f', struct.pack('I', int_rep))[0]    #转float
            gameval = round(f * 100)
            self.displayval = str(gameval)

    def set_value(self, thedata):
        self.displayval = thedata
        content = b''

        if self.datastyle == "dec1byte":
            i = int(self.displayval)
            content = i.to_bytes(1, 'little')
        elif self.datastyle == "fullname":
            hex_str = self.ASCIItoHex(self.displayval)
            content = bytes.fromhex(hex_str)
            self.card.save_name_ints(len(content))
        elif self.datastyle == "hex":
            content = bytes.fromhex(self.displayval)
        elif self.datastyle == "color":
            idx = int(self.end)
            f = float(self.displayval) / 255 if idx < 3 else float(self.displayval) / 100
            content = f.to_bytes(4, 'big')
        elif self.datastyle == "normal":
            f = float(self.displayval) / 100
            packed = struct.pack('f', f)
            hexes = [byte for byte in packed]
            hexes.reverse()
            content = hexes
        
        edr = self.end 
        if self.datastyle == "dec1byte":
            edr = "1byte"
        self.card.update_change_to_databytes(content, self.pos, edr)
        if self.datastyle=="fullname":
            #update all
            self.card.update_all()
    
    def get_value(self):
        return self.displayval
    
    
class Card:
    def __init__(self):
        self.picbytes = None      #人物卡图像二进制数据
        self.databytes = None   #人物卡信息二进制数据  
        self.fullnameIntsPos = [0]*8
        self.fullnameInts = [0]*8
        self.data = {           #人物卡信息格式化数据
            "txt_charName": Charstat(self, "txt_charName", "fullname", "fullname", 1, "ab"),
            "txt_birthMonth":Charstat(self,"txt_birthMonth", "dec1byte", "birthMonth", 0, "a8"),
            "txt_birthDay": Charstat(self,"txt_birthDay", "dec1byte", "birthDay", 0, "a9"),
            "txt_personality" : Charstat(self,"txt_personality", "dec1byte", "personality", 0, "instance01"),
            "txt_trait" : Charstat(self,"txt_trait", "dec1byte", "trait", 0, "a4"),
            "txt_mentality" : Charstat(self,"txt_mentality", "dec1byte", "mind", 0, "aa"),
            "txt_sextrait" : Charstat(self,"txt_sextrait", "dec1byte", "hAttribute", 0, "b0"),
            "txt_favor" : Charstat(self,"txt_favor", "dec1byte", "Favor", 0, "a9",finders_favor,"sld_favor"),
            "txt_slavery" : Charstat(self,"txt_slavery", "dec1byte", "Slavery", 0, "a6",None,"sld_slavery"),
            "txt_enjoyment" : Charstat(self,"txt_enjoyment", "dec1byte", "Enjoyment", 0, "a8",None,"sld_enjoyment"),
            "txt_aversion" : Charstat(self,"txt_aversion", "dec1byte", "Aversion", 0, "a7",None,"sld_aversion"),
            "txt_dependence" : Charstat(self,"txt_dependence", "dec1byte", "Dependence", 0, "a5",None,"sld_dependence"),
            "txt_broken" : Charstat(self,"txt_broken", "dec1byte", "Broken", 0, "a5", None, "sld_broken"),
            "txt_voiceRate" : Charstat(self,"txt_voiceRate", "normal", "voiceRate",0,"instance01",None,"sld_voiceRate"), #need to get 2nd instance
            #/read Futanari
            #c2 for no, c3 for yes
            "txt_futastate" : Charstat(self,"txt_futastate", "hex", "futanari", 0, "b0"),
            #/START HAIR DATA#/
            #hair checkboxes
            "txt_match_hair" : Charstat(self,"txt_match_hair", "hex", "sameSetting", 0, "ab"),
            "txt_auto_hair_color" : Charstat(self,"txt_auto_hair_color", "hex", "autoSetting", 0, "ac"),
            "txt_hair_axis_ctrl" : Charstat(self,"txt_hair_axis_ctrl", "hex", "ctrlTogether", 0, "a5"),
            #hair types
            #txt_backHairType txt_bangsType txt_sideHairType txt_hairExtType
            
            # Charstat(self,"txt_backHairType", "hex", "sameSetting", 0, "ab"),
            # Charstat(self,"txt_bangsType", "hex", "sameSetting", 0, "ab"),
            # Charstat(self,"txt_sideHairType", "hex", "sameSetting", 0, "ab"),
            # Charstat(self,"txt_hairExtType", "hex", "sameSetting", 0, "ab"),
            
            #/START HEAD DATA#/
            #read Eye Shadow data
            "txt_eyeshadowType" : Charstat(self,"txt_eyeshadowType", "hex", "eyeshadowId", 0, "ae"),
            "txt_eyeshadowRed" : Charstat(self,"txt_eyeshadowRed","color","eyeshadowColor",1,"0"),
            "txt_eyeshadowGreen" : Charstat(self,"txt_eyeshadowGreen","color","eyeshadowColor",1,"1"),
            "txt_eyeshadowBlue" : Charstat(self,"txt_eyeshadowBlue","color","eyeshadowColor",1,"2"),
            "txt_eyeshadowAlpha" : Charstat(self,"txt_eyeshadowAlpha","color","eyeshadowColor",1,"3"),
            "txt_eyeshadowShine" : Charstat(self,"txt_eyeshadowShine", "normal", "eyeshadowGloss"),
            #read Cheeks data
            "txt_cheekType" : Charstat(self,"txt_cheekType", "hex", "cheekId", 0, "aa"),
            "txt_cheekRed" : Charstat(self,"txt_cheekRed","color","cheekColor",1,"0"),
            "txt_cheekGreen" : Charstat(self,"txt_cheekGreen","color","cheekColor",1,"1"),
            "txt_cheekBlue" : Charstat(self,"txt_cheekBlue","color","cheekColor",1,"2"),
            "txt_cheekAlpha" : Charstat(self,"txt_cheekAlpha","color","cheekColor",1,"3"),
            "txt_cheekShine" : Charstat(self,"txt_cheekShine", "normal", "cheekGloss"),
            #read Lips data
            "txt_lipType" : Charstat(self,"txt_lipType", "hex", "lipId", 0, "a8"),
            "txt_lipRed" : Charstat(self,"txt_lipRed","color","lipColor",1,"0"),
            "txt_lipGreen" : Charstat(self,"txt_lipGreen","color","lipColor",1,"1"),
            "txt_lipBlue" : Charstat(self,"txt_lipBlue","color","lipColor",1,"2"),
            "txt_lipAlpha" : Charstat(self,"txt_lipAlpha","color","lipColor",1,"3"),
            "txt_lipShine" : Charstat(self,"txt_lipShine", "normal", "lipGloss"),

            #read Face Paint 1 data
            "txt_paintf1Type" : Charstat(self,"txt_paintf1Type", "hex", "id", 0, "a5", finders_facepaint1),
            "txt_paintf1Red" : Charstat(self,"txt_paintf1Red","color","color",1,"0", finders_facepaint1),
            "txt_paintf1Green" : Charstat(self,"txt_paintf1Green","color","color",1,"1", finders_facepaint1),
            "txt_paintf1Blue" : Charstat(self,"txt_paintf1Blue","color","color",1,"2", finders_facepaint1),
            "txt_paintf1Alpha" : Charstat(self,"txt_paintf1Alpha","color","color",1,"3", finders_facepaint1),
            "txt_paintf1Shine" : Charstat(self,"txt_paintf1Shine", "normal", "glossPower",0,"", finders_facepaint1),
            "txt_paintf1Texture" : Charstat(self,"txt_paintf1Texture", "normal", "metallicPower",0,"", finders_facepaint1),
            "txt_paintf1Position" : Charstat(self,"txt_paintf1Position", "hex", "layoutId", 0, "a6", finders_facepaint1),
            "txt_paintf1Width" : Charstat(self,"txt_paintf1Width", "normal", "layout", 1,"", finders_facepaint1a),
            "txt_paintf1Height" : Charstat(self,"txt_paintf1Height", "normal", "layout", 6,"", finders_facepaint1a),
            "txt_paintf1PosX" : Charstat(self,"txt_paintf1PosX", "normal", "layout", 11,"", finders_facepaint1a),
            "txt_paintf1PosY" : Charstat(self,"txt_paintf1PosY", "normal", "layout", 16,"", finders_facepaint1a),
            "txt_paintf1Rotation" : Charstat(self,"txt_paintf1Rotation", "normal", "rotation", 0,"", finders_facepaint1a),
            #read Face Paint 2 data
            "txt_paintf2Type" : Charstat(self,"txt_paintf2Type", "hex", "id", 0, "a5", finders_facepaint2),
            "txt_paintf2Red" : Charstat(self,"txt_paintf2Red","color","color",1,"0", finders_facepaint2),
            "txt_paintf2Green" : Charstat(self,"txt_paintf2Green","color","color",1,"1", finders_facepaint2),
            "txt_paintf2Blue" : Charstat(self,"txt_paintf2Blue","color","color",1,"2", finders_facepaint2),
            "txt_paintf2Alpha" : Charstat(self,"txt_paintf2Alpha","color","color",1,"3", finders_facepaint2),
            "txt_paintf2Shine" : Charstat(self,"txt_paintf2Shine", "normal", "glossPower",0,"", finders_facepaint2),
            "txt_paintf2Texture" : Charstat(self,"txt_paintf2Texture", "normal", "metallicPower",0,"", finders_facepaint2),
            "txt_paintf2Position" : Charstat(self,"txt_paintf2Position", "hex", "layoutId", 0, "a6", finders_facepaint2),
            "txt_paintf2Width" : Charstat(self,"txt_paintf2Width", "normal", "layout", 1,"", finders_facepaint2a),
            "txt_paintf2Height" : Charstat(self,"txt_paintf2Height", "normal", "layout", 6,"", finders_facepaint2a),
            "txt_paintf2PosX" : Charstat(self,"txt_paintf2PosX", "normal", "layout", 11,"", finders_facepaint2a),
            "txt_paintf2PosY" : Charstat(self,"txt_paintf2PosY", "normal", "layout", 16,"", finders_facepaint2a),
            "txt_paintf2Rotation" : Charstat(self,"txt_paintf2Rotation", "normal", "rotation", 0,"", finders_facepaint2a),

            #read Left/Right Eye data
            #weirdly, pupil = iris, black = pupil, and whites = whites.
            "txt_leftIrisType" : Charstat(self,"txt_leftIrisType", "hex", "pupilId", 0, "aa"),
            "txt_rightIrisType" : Charstat(self,"txt_rightIrisType", "hex", "pupilId", 0, "aa", finders_righteye),
            "txt_leftIrisRed" : Charstat(self,"txt_leftIrisRed", "color", "pupilColor", 1, "0"),
            "txt_leftIrisGreen" : Charstat(self,"txt_leftIrisGreen", "color", "pupilColor", 1, "1"),
            "txt_leftIrisBlue" : Charstat(self,"txt_leftIrisBlue", "color", "pupilColor", 1, "2"),
            "txt_leftIrisAlpha" : Charstat(self,"txt_leftIrisAlpha", "color", "pupilColor", 1, "3"),
            "txt_rightIrisRed" : Charstat(self,"txt_rightIrisRed", "color", "pupilColor", 1, "0", finders_righteye),
            "txt_rightIrisGreen" : Charstat(self,"txt_rightIrisGreen", "color", "pupilColor", 1, "1", finders_righteye),
            "txt_rightIrisBlue" : Charstat(self,"txt_rightIrisBlue", "color", "pupilColor", 1, "2", finders_righteye),
            "txt_rightIrisAlpha" : Charstat(self,"txt_rightIrisAlpha", "color", "pupilColor", 1, "3", finders_righteye),
            "txt_leftIrisGlow" : Charstat(self,"txt_leftIrisGlow", "normal", "pupilEmission", 0),
            "txt_leftIrisWidth" : Charstat(self,"txt_leftIrisWidth", "normal", "pupilW", 0),
            "txt_leftIrisHeight" : Charstat(self,"txt_leftIrisHeight", "normal", "pupilH", 0),
            "txt_rightIrisGlow" : Charstat(self,"txt_rightIrisGlow", "normal", "pupilEmission", 0, "", finders_righteye),
            "txt_rightIrisWidth" : Charstat(self,"txt_rightIrisWidth", "normal", "pupilW", 0, "", finders_righteye),
            "txt_rightIrisHeight" : Charstat(self,"txt_rightIrisHeight", "normal", "pupilH", 0, "", finders_righteye),
            "txt_leftPupilType" : Charstat(self,"txt_leftPupilType", "hex", "blackId", 0, "aa"),
            "txt_rightPupilType" : Charstat(self,"txt_rightPupilType", "hex", "blackId", 0, "aa", finders_righteye),
            "txt_leftPupilRed" : Charstat(self,"txt_leftPupilRed", "color", "blackColor", 1, "0"),
            "txt_leftPupilGreen" : Charstat(self,"txt_leftPupilGreen", "color", "blackColor", 1, "1"),
            "txt_leftPupilBlue" : Charstat(self,"txt_leftPupilBlue", "color", "blackColor", 1, "2"),
            "txt_leftPupilAlpha" : Charstat(self,"txt_leftPupilAlpha", "color", "blackColor", 1, "3"),
            "txt_rightPupilRed" : Charstat(self,"txt_rightPupilRed", "color", "blackColor", 1, "0", finders_righteye),
            "txt_rightPupilGreen" : Charstat(self,"txt_rightPupilGreen", "color", "blackColor", 1, "1", finders_righteye),
            "txt_rightPupilBlue" : Charstat(self,"txt_rightPupilBlue", "color", "blackColor", 1, "2", finders_righteye),
            "txt_rightPupilAlpha" : Charstat(self,"txt_rightPupilAlpha", "color", "blackColor", 1, "3", finders_righteye),
            "txt_leftPupilWidth" : Charstat(self,"txt_leftPupilWidth", "normal", "blackW", 0),
            "txt_leftPupilHeight" : Charstat(self,"txt_leftPupilHeight", "normal", "blackH", 0),
            "txt_rightPupilWidth" : Charstat(self,"txt_rightPupilWidth", "normal", "blackW", 0, "", finders_righteye),
            "txt_rightPupilHeight" : Charstat(self,"txt_rightPupilHeight", "normal", "blackH", 0, "", finders_righteye),
            "txt_leftWhitesRed" : Charstat(self,"txt_leftWhitesRed", "color", "whiteColor", 1, "0"),
            "txt_leftWhitesGreen" : Charstat(self,"txt_leftWhitesGreen", "color", "whiteColor", 1, "1"),
            "txt_leftWhitesBlue" : Charstat(self,"txt_leftWhitesBlue", "color", "whiteColor", 1, "2"),
            "txt_leftWhitesAlpha" : Charstat(self,"txt_leftWhitesAlpha", "color", "whiteColor", 1, "3"),
            "txt_rightWhitesRed" : Charstat(self,"txt_rightWhitesRed", "color", "whiteColor", 1, "0", finders_righteye_whites),
            "txt_rightWhitesGreen" : Charstat(self,"txt_rightWhitesGreen", "color", "whiteColor", 1, "1", finders_righteye_whites),
            "txt_rightWhitesBlue" : Charstat(self,"txt_rightWhitesBlue", "color", "whiteColor", 1, "2", finders_righteye_whites),
            "txt_rightWhitesAlpha" : Charstat(self,"txt_rightWhitesAlpha", "color", "whiteColor", 1, "3", finders_righteye_whites),

            #read Iris Settings data
            "txt_irisHeightAdj" : Charstat(self,"txt_irisHeightAdj", "normal", "pupilY", 0),
            "txt_irisShadow" : Charstat(self,"txt_irisShadow", "normal", "pupilH", 0),

            #read Eye Highlights data
            "txt_hlType" : Charstat(self,"txt_hlType", "hex", "hlId", 0, "a7"),
            "txt_hlRed" : Charstat(self,"txt_hlRed", "color", "hlColor", 1, "0"),
            "txt_hlGreen" : Charstat(self,"txt_hlGreen", "color", "hlColor", 1, "1"),
            "txt_hlBlue" : Charstat(self,"txt_hlBlue", "color", "hlColor", 1, "2"),
            "txt_hlAlpha" : Charstat(self,"txt_hlAlpha", "color", "hlColor", 1, "3"),
            "txt_hlWidth" : Charstat(self,"txt_hlWidth", "normal", "hlLayout", 1),
            "txt_hlHeight" : Charstat(self,"txt_hlHeight", "normal", "hlLayout", 6),
            "txt_hlXAxis" : Charstat(self,"txt_hlXAxis", "normal", "hlLayout", 11),
            "txt_hlYAxis" : Charstat(self,"txt_hlYAxis", "normal", "hlLayout", 16),
            "txt_hlTilt" : Charstat(self,"txt_hlTilt", "normal", "hlTilt", 0),

            #read Eyebrow Type data
            "txt_eyebrowType" : Charstat(self,"txt_eyebrowType", "hex", "eyebrowId", 0, "ac"),
            "txt_eyebrowRed" : Charstat(self,"txt_eyebrowRed", "color", "eyebrowColor", 1, "0"),
            "txt_eyebrowGreen" : Charstat(self,"txt_eyebrowGreen", "color", "eyebrowColor", 1, "1"),
            "txt_eyebrowBlue" : Charstat(self,"txt_eyebrowBlue", "color", "eyebrowColor", 1, "2"),
            "txt_eyebrowAlpha" : Charstat(self,"txt_eyebrowAlpha", "color", "eyebrowColor", 1, "3"),

            #read Eyelash Type data
            "txt_eyelashType" : Charstat(self,"txt_eyelashType", "hex", "eyelashesId", 0, "ae"),
            "txt_eyelashRed" : Charstat(self,"txt_eyelashRed", "color", "eyelashesColor", 1, "0"),
            "txt_eyelashGreen" : Charstat(self,"txt_eyelashGreen", "color", "eyelashesColor", 1, "1"),
            "txt_eyelashBlue" : Charstat(self,"txt_eyelashBlue", "color", "eyelashesColor", 1, "2"),
            "txt_eyelashAlpha" : Charstat(self,"txt_eyelashAlpha", "color", "eyelashesColor", 1, "3"),

            #read Facial Type data
            "txt_headContour" : Charstat(self,"txt_headContour", "hex", "headId", 0, "a6"),
            "txt_headSkin" : Charstat(self,"txt_headSkin", "hex", "skinId", 0, "a8", finders_facetype),
            "txt_headWrinkles" : Charstat(self,"txt_headWrinkles", "hex", "detailId", 0, "ab", finders_facetype ),
            "txt_headWrinkleIntensity" : Charstat(self,"txt_headWrinkleIntensity", "normal", "detailPower", 0,"", finders_facetype),
            
            #read Overall data
            "全脸宽度" : Charstat(self,"txt_headWidth", "normal", "shapeValueFace", 3),
            "脸上部前后位置" : Charstat(self,"txt_headUpperDepth", "normal", "shapeValueFace", 8),
            "脸部上方和下方" : Charstat(self,"txt_headUpperHeight", "normal", "shapeValueFace", 13),
            "下脸前后位置" : Charstat(self,"txt_headLowerDepth", "normal", "shapeValueFace", 18),
            "脸下部宽度" : Charstat(self,"txt_headLowerWidth", "normal", "shapeValueFace", 23),
            #read Jaw data
            "下颚宽度" : Charstat(self,"txt_jawWidth", "normal", "shapeValueFace", 28),
            "下巴上下位置1" : Charstat(self,"txt_jawHeight", "normal", "shapeValueFace", 33),
            "下巴前后位置" : Charstat(self,"txt_jawDepth", "normal", "shapeValueFace", 38),
            "下颚角度" : Charstat(self,"txt_jawAngle", "normal", "shapeValueFace", 43),
            "下颚底部上下位置" : Charstat(self,"txt_neckDroop", "normal", "shapeValueFace", 48),
            "下巴宽度" : Charstat(self,"txt_chinSize", "normal", "shapeValueFace", 53),
            "下巴上下位置2" : Charstat(self,"txt_chinHeight", "normal", "shapeValueFace", 58),
            "下巴前后" : Charstat(self,"txt_chinDepth", "normal", "shapeValueFace", 63),
            #read Mole data
            "txt_moleID" : Charstat(self,"txt_moleID", "hex", "moleId", 0, "a9"),
            "txt_moleWidth" : Charstat(self,"txt_moleWidth", "normal", "moleLayout", 1),
            "txt_moleHeight" : Charstat(self,"txt_moleHeight", "normal", "moleLayout", 6),
            "txt_molePosX" : Charstat(self,"txt_molePosX", "normal", "moleLayout", 11),
            "txt_molePosY" : Charstat(self,"txt_molePosY", "normal", "moleLayout", 16),
            "txt_moleRed" : Charstat(self,"txt_moleRed", "color", "moleColor", 1, "0"),
            "txt_moleGreen" : Charstat(self,"txt_moleGreen", "color", "moleColor", 1, "1"),
            "txt_moleBlue" : Charstat(self,"txt_moleBlue", "color", "moleColor", 1, "2"),
            "txt_moleAlpha" : Charstat(self,"txt_moleAlpha", "color", "moleColor", 1, "3"),
            #read Cheeks data
            "脸颊下部上下位置" : Charstat(self,"txt_cheekLowerHeight", "normal", "shapeValueFace", 68),
            "下颊前后" : Charstat(self,"txt_cheekLowerDepth", "normal", "shapeValueFace", 73),
            "下颊宽度" : Charstat(self,"txt_cheekLowerWidth", "normal", "shapeValueFace", 78),
            "脸颊上部上下位置" : Charstat(self,"txt_cheekUpperHeight", "normal", "shapeValueFace", 83),
            "上颊前后" : Charstat(self,"txt_cheekUpperDepth", "normal", "shapeValueFace", 88),
            "脸上部宽度" : Charstat(self,"txt_cheekUpperWidth", "normal", "shapeValueFace", 93),
            #read Eyebrows data
            "眉位置X" : Charstat(self,"txt_browPosX", "normal", "eyebrowLayout", 1),
            "眉位置Y" : Charstat(self,"txt_browPosY", "normal", "eyebrowLayout", 6),
            "眉宽" : Charstat(self,"txt_browWidth", "normal", "eyebrowLayout", 11),
            "眉高" : Charstat(self,"txt_browHeight", "normal", "eyebrowLayout", 16),
            "眉毛倾斜" : Charstat(self,"txt_browAngle", "normal", "eyebrowTilt"),
            #read Eyes data
            "眼睛上下" : Charstat(self,"txt_eyeVertical", "normal", "shapeValueFace", 98),
            "眼位" : Charstat(self,"txt_eyeSpacing", "normal", "shapeValueFace", 103),
            "眼睛前后" : Charstat(self,"txt_eyeDepth", "normal", "shapeValueFace", 108),
            "眼宽1" : Charstat(self,"txt_eyeWidth", "normal", "shapeValueFace", 113),
            "眼宽2" : Charstat(self,"txt_eyeHeight", "normal", "shapeValueFace", 118),
            "眼角z轴" : Charstat(self,"txt_eyeAngleZ", "normal", "shapeValueFace", 123),
            "眼角y轴" : Charstat(self,"txt_eyeAngleY", "normal", "shapeValueFace", 128),
            "左右眼位置1" : Charstat(self,"txt_eyeInnerDist", "normal", "shapeValueFace", 133),
            "左右眼位置2" : Charstat(self,"txt_eyeOuterDist", "normal", "shapeValueFace", 138),
            "眼角上下位置1" : Charstat(self,"txt_eyeInnerHeight", "normal", "shapeValueFace", 143),
            "眼角上下位置2" : Charstat(self,"txt_eyeOuterHeight", "normal", "shapeValueFace", 148),
            "眼皮形状1" : Charstat(self,"txt_eyelidShape1", "normal", "shapeValueFace", 153),
            "眼皮形状2" : Charstat(self,"txt_eyelidShape2", "normal", "shapeValueFace", 158),
            "txt_eyeOpenMax" : Charstat(self,"txt_eyeOpenMax", "normal", "eyesOpenMax"),
            #read Nose data
            "整个鼻子上下位置" : Charstat(self,"txt_noseHeight", "normal", "shapeValueFace", 163),
            "整个鼻子前后" : Charstat(self,"txt_noseDepth", "normal", "shapeValueFace", 168),
            "鼻子整体角度X轴" : Charstat(self,"txt_noseAngle", "normal", "shapeValueFace", 173),
            "鼻子的整个宽度" : Charstat(self,"txt_noseSize", "normal", "shapeValueFace", 178),
            "鼻梁高度" : Charstat(self,"txt_bridgeHeight", "normal", "shapeValueFace", 183),
            "鼻梁宽度" : Charstat(self,"txt_bridgeWidth", "normal", "shapeValueFace", 188),
            "鼻梁形状" : Charstat(self,"txt_bridgeShape", "normal", "shapeValueFace", 193),
            "鼻宽" : Charstat(self,"txt_nostrilWidth", "normal", "shapeValueFace", 198),
            "上下鼻子" : Charstat(self,"txt_nostrilHeight", "normal", "shapeValueFace", 203),
            "鼻子前后" : Charstat(self,"txt_nostrilLength", "normal", "shapeValueFace", 208),
            "鼻头角度X轴" : Charstat(self,"txt_nostrilInnerWidth", "normal", "shapeValueFace", 213),
            "鼻头角度Z轴" : Charstat(self,"txt_nostrilOuterWidth", "normal", "shapeValueFace", 218),
            "鼻子高度" : Charstat(self,"txt_noseTipLength", "normal", "shapeValueFace", 223),
            "鼻尖X轴" : Charstat(self,"txt_noseTipHeight", "normal", "shapeValueFace", 228),
            "鼻尖大小" : Charstat(self,"txt_noseTipSize", "normal", "shapeValueFace", 233),
            #read Mouth data
            "嘴上下" : Charstat(self,"txt_mouthHeight", "normal", "shapeValueFace", 238),
            "口宽" : Charstat(self,"txt_mouthWidth", "normal", "shapeValueFace", 243),
            "嘴唇宽度" : Charstat(self,"txt_lipThickness", "normal", "shapeValueFace", 248),
            "嘴前后位置" : Charstat(self,"txt_mouthDepth", "normal", "shapeValueFace", 253),
            "上嘴唇形" : Charstat(self,"txt_upperLipThick", "normal", "shapeValueFace", 258),
            "下嘴唇形" : Charstat(self,"txt_lowerLipThick", "normal", "shapeValueFace", 263),
            "嘴型嘴角" : Charstat(self,"txt_mouthCorners", "normal", "shapeValueFace", 268),
            
            #read Ears data
            "txt_earSize" : Charstat(self,"txt_earSize", "normal", "shapeValueFace", 273),
            "txt_earAngle" : Charstat(self,"txt_earAngle", "normal", "shapeValueFace", 278),
            "txt_earRotation" : Charstat(self,"txt_earRotation", "normal", "shapeValueFace", 283),
            "txt_earUpShape" : Charstat(self,"txt_earUpShape", "normal", "shapeValueFace", 288),
            "txt_lowEarShape" : Charstat(self,"txt_lowEarShape", "normal", "shapeValueFace", 293),
            #/START BODY DATA#/
            #read Overall data
            "txt_ovrlHeight" : Charstat(self,"txt_ovrlHeight", "normal", "shapeValueBody", 3),
            "txt_headSize" : Charstat(self,"txt_headSize", "normal", "shapeValueBody", 48),
            #read Breast data
            "txt_bustSize" : Charstat(self,"txt_bustSize", "normal", "shapeValueBody", 8),
            "txt_bustHeight" : Charstat(self,"txt_bustHeight", "normal", "shapeValueBody", 13),
            "txt_bustDirection" : Charstat(self,"txt_bustDirection", "normal", "shapeValueBody", 18),
            "txt_bustSpacing" : Charstat(self,"txt_bustSpacing", "normal", "shapeValueBody", 23),
            "txt_bustAngle" : Charstat(self,"txt_bustAngle", "normal", "shapeValueBody", 28),
            "txt_bustLength" : Charstat(self,"txt_bustLength", "normal", "shapeValueBody", 33),
            "txt_areolaSize" : Charstat(self,"txt_areolaSize", "normal", "areolaSize"),
            "txt_areolaDepth" : Charstat(self,"txt_areolaDepth", "normal", "shapeValueBody", 38),
            "txt_bustSoftness" : Charstat(self,"txt_bustSoftness", "normal", "bustSoftness"),
            "txt_bustWeight" : Charstat(self,"txt_bustWeight", "normal", "bustWeight"),
            "txt_nippleWidth" : Charstat(self,"txt_nippleWidth", "normal", "shapeValueBody", 43),
            "txt_nippleDepth" : Charstat(self,"txt_nippleDepth", "normal", "bustSoftness", -18),
            #read Upper Body data
            "txt_neckWidth" : Charstat(self,"txt_neckWidth", "normal", "shapeValueBody", 53),
            "txt_neckThickness" : Charstat(self,"txt_neckThickness", "normal", "shapeValueBody", 58),
            "txt_shoulderWidth" : Charstat(self,"txt_shoulderWidth", "normal", "shapeValueBody", 63),
            "txt_shoulderThickness" : Charstat(self,"txt_shoulderThickness", "normal", "shapeValueBody", 68),
            "txt_chestWidth" : Charstat(self,"txt_chestWidth", "normal", "shapeValueBody", 73),
            "txt_chestThickness" : Charstat(self,"txt_chestThickness", "normal", "shapeValueBody", 78),
            "txt_waistWidth" : Charstat(self,"txt_waistWidth", "normal", "shapeValueBody", 83),
            "txt_waistThickness" : Charstat(self,"txt_waistThickness", "normal", "shapeValueBody", 88),
            #read Lower body data
            "txt_waistHeight" : Charstat(self,"txt_waistHeight", "normal", "shapeValueBody", 93),
            "txt_pelvisWidth" : Charstat(self,"txt_pelvisWidth", "normal", "shapeValueBody", 98),
            "txt_pelvisThickness" : Charstat(self,"txt_pelvisThickness", "normal", "shapeValueBody", 103),
            "txt_hipsWidth" : Charstat(self,"txt_hipsWidth", "normal", "shapeValueBody", 108),
            "txt_hipsThickness" : Charstat(self,"txt_hipsThickness", "normal", "shapeValueBody", 113),
            "txt_buttSize" : Charstat(self,"txt_buttSize", "normal", "shapeValueBody", 118),
            "txt_buttAngle" : Charstat(self,"txt_buttAngle", "normal", "shapeValueBody", 123),
            #read Arms data
            "txt_shoulderSize" : Charstat(self,"txt_shoulderSize", "normal", "shapeValueBody", 148),
            "txt_upperArms" : Charstat(self,"txt_upperArms", "normal", "shapeValueBody", 153),
            "txt_forearm" : Charstat(self,"txt_forearm", "normal", "shapeValueBody", 158),
            #read Legs data
            "txt_thighs" : Charstat(self,"txt_thighs", "normal", "shapeValueBody", 128),
            "txt_legs" : Charstat(self,"txt_legs", "normal", "shapeValueBody", 133),
            "txt_calves" : Charstat(self,"txt_calves", "normal", "shapeValueBody", 138),
            "txt_ankles" : Charstat(self,"txt_ankles", "normal", "shapeValueBody", 143),

            #/START SKIN DATA#/
            #read Skin Type data
            "txt_skinType": Charstat(self,"txt_skinType", "hex", "skinId", 0, "a8", finders_skintype ), #start searching after bustWeight to avoid grabbing head data instead of body
            "txt_skinBuild": Charstat(self,"txt_skinBuild", "hex", "detailId", 0, "ab", finders_skintype),
            "txt_skinBuildDef": Charstat(self,"txt_skinBuildDef", "normal", "detailPower", 0, "", finders_skintype),
            "txt_skinRed": Charstat(self,"txt_skinRed", "color", "skinColor", 1, "0"),
            "txt_skinGreen": Charstat(self,"txt_skinGreen", "color", "skinColor", 1, "1"),
            "txt_skinBlue": Charstat(self,"txt_skinBlue", "color", "skinColor", 1, "2"),
            "txt_skinShine": Charstat(self,"txt_skinShine", "normal", "skinGlossPower"),
            "txt_skinTexture": Charstat(self,"txt_skinTexture", "normal", "skinMetallicPower"),
            #read Suntan data
            "txt_tanType": Charstat(self,"txt_tanType", "hex", "sunburnId", 0, "ac"),
            "txt_tanRed": Charstat(self,"txt_tanRed", "color", "sunburnColor", 1, "0"),
            "txt_tanGreen": Charstat(self,"txt_tanGreen", "color", "sunburnColor", 1, "1"),
            "txt_tanBlue": Charstat(self,"txt_tanBlue", "color", "sunburnColor", 1, "2"),
            "txt_tanAlpha": Charstat(self,"txt_tanAlpha", "color", "sunburnColor", 1, "3"),
            #read Nipple Skin data
            "txt_nipType": Charstat(self,"txt_nipType", "hex", "nipId", 0, "a8"),
            "txt_nipRed": Charstat(self,"txt_nipRed", "color", "nipColor", 1, "0"),
            "txt_nipGreen": Charstat(self,"txt_nipGreen", "color", "nipColor", 1, "1"),
            "txt_nipBlue": Charstat(self,"txt_nipBlue", "color", "nipColor", 1, "2"),
            "txt_nipAlpha": Charstat(self,"txt_nipAlpha", "color", "nipColor", 1, "3"),
            "txt_nipShine": Charstat(self,"txt_nipShine", "normal", "nipGlossPower"),
            #read Pubic Hair data
            "txt_pubeType": Charstat(self,"txt_pubeType", "hex", "underhairId", 0, "ae"),
            "txt_pubeRed": Charstat(self,"txt_pubeRed", "color", "underhairColor", 1, "0"),
            "txt_pubeGreen": Charstat(self,"txt_pubeGreen", "color", "underhairColor", 1, "1"),
            "txt_pubeBlue": Charstat(self,"txt_pubeBlue", "color", "underhairColor", 1, "2"),
            "txt_pubeAlpha": Charstat(self,"txt_pubeAlpha", "color", "underhairColor", 1, "3"),
            #read Fingernail data
            "txt_nailRed": Charstat(self,"txt_nailRed", "color", "nailColor", 1, "0"),
            "txt_nailGreen": Charstat(self,"txt_nailGreen", "color", "nailColor", 1, "1"),
            "txt_nailBlue": Charstat(self,"txt_nailBlue", "color", "nailColor", 1, "2"),
            "txt_nailAlpha": Charstat(self,"txt_nailAlpha", "color", "nailColor", 1, "3"),
            "txt_nailShine": Charstat(self,"txt_nailShine", "normal", "nailGlossPower"),

            #read Body Paint 1 data
            "txt_paint1Type" : Charstat(self,"txt_paint1Type", "hex", "id", 0, "a5",finders_bodypaint1),
            "txt_paint1Red" : Charstat(self,"txt_paint1Red","color","color",1,"0",finders_bodypaint1),
            "txt_paint1Green" : Charstat(self,"txt_paint1Green","color","color",1,"1",finders_bodypaint1),
            "txt_paint1Blue" : Charstat(self,"txt_paint1Blue","color","color",1,"2", finders_bodypaint1),
            "txt_paint1Alpha" : Charstat(self,"txt_paint1Alpha","color","color",1,"3", finders_bodypaint1),
            "txt_paint1Shine" : Charstat(self,"txt_paint1Shine", "normal", "glossPower",0,"", finders_bodypaint1),
            "txt_paint1Texture" : Charstat(self,"txt_paint1Texture", "normal", "metallicPower",0,"", finders_bodypaint1),
            "txt_paint1Position" : Charstat(self,"txt_paint1Position", "hex", "layoutId", 0, "a6", finders_bodypaint1),
            "txt_paint1Width" : Charstat(self,"txt_paint1Width", "normal", "layout", 1,"", finders_bodypaint1a),
            "txt_paint1Height" : Charstat(self,"txt_paint1Height", "normal", "layout", 6,"", finders_bodypaint1a),
            "txt_paint1PosX" : Charstat(self,"txt_paint1PosX", "normal", "layout", 11,"", finders_bodypaint1a),
            "txt_paint1PosY" : Charstat(self,"txt_paint1PosY", "normal", "layout", 16,"", finders_bodypaint1a),
            "txt_paint1Rotation" : Charstat(self,"txt_paint1Rotation", "normal", "rotation", 0,"", finders_bodypaint1a),
            #read Body Paint 2 data
            "txt_paint2Type" : Charstat(self,"txt_paint2Type", "hex", "id", 0, "a5",finders_bodypaint2),
            "txt_paint2Red" : Charstat(self,"txt_paint2Red","color","color",1,"0",finders_bodypaint2),
            "txt_paint2Green" : Charstat(self,"txt_paint2Green","color","color",1,"1",finders_bodypaint2),
            "txt_paint2Blue" : Charstat(self,"txt_paint2Blue","color","color",1,"2", finders_bodypaint2),
            "txt_paint2Alpha" : Charstat(self,"txt_paint2Alpha","color","color",1,"3", finders_bodypaint2),
            "txt_paint2Shine" : Charstat(self,"txt_paint2Shine", "normal", "glossPower",0,"", finders_bodypaint2),
            "txt_paint2Texture" : Charstat(self,"txt_paint2Texture", "normal", "metallicPower",0,"", finders_bodypaint2),
            "txt_paint2Position" : Charstat(self,"txt_paint2Position", "hex", "layoutId", 0, "a6", finders_bodypaint2),
            "txt_paint2Width" : Charstat(self,"txt_paint2Width", "normal", "layout", 1,"", finders_bodypaint2a),
            "txt_paint2Height" : Charstat(self,"txt_paint2Height", "normal", "layout", 6,"", finders_bodypaint2a),
            "txt_paint2PosX" : Charstat(self,"txt_paint2PosX", "normal", "layout", 11,"", finders_bodypaint2a),
            "txt_paint2PosY" : Charstat(self,"txt_paint2PosY", "normal", "layout", 16,"", finders_bodypaint2a),
            "txt_paint2Rotation" : Charstat(self,"txt_paint2Rotation", "normal", "rotation", 0,"", finders_bodypaint2a)
        }   

    #加载人物卡
    def load_card(self, cardfile):
        with open(cardfile, 'rb') as file:
            filebytes = file.read()

        # separate the data from the image
        searchfor = b"IEND"
        iend_pos = filebytes.find(searchfor)
        self.picbytes = filebytes[:iend_pos + 8]
        self.databytes = filebytes[iend_pos + 8:]

        if len(self.databytes) == 0:
            print("Card Read Error \n The PNG you selected has no card data")
            return

        # load all stats from card data to text boxes
        for key in self.data:
            self.data[key].load_data(self.databytes)
            
        oldnamelen = len(self.data['txt_charName'].displayval)
        searchfor = b"pos"
        self.fullnameIntsPos[0] = search(self.databytes, searchfor) + 4
        self.fullnameIntsPos[1] = search(self.databytes, searchfor, 4) + 4
        self.fullnameIntsPos[2] = search(self.databytes, searchfor, 5) + 4
        self.fullnameIntsPos[3] = search(self.databytes, searchfor, 6) + 4
        self.fullnameIntsPos[4] = search(self.databytes, searchfor, 7) + 4
        searchfor = b"size"
        self.fullnameIntsPos[5] = search(self.databytes, searchfor, 3) + 4 #this one is 1 byte only
        self.fullnameIntsPos[6] = search(self.databytes, searchfor, 7) + 6
        searchfor = b"fullname"
        self.fullnameIntsPos[7] = search(self.databytes, searchfor) + 8 #this one is 1 byte only

        for i in range(8):
            if (i == 5) or (i == 7):
                j = 1
            else:
                j = 2
            
            hex_num = self.databytes[self.fullnameIntsPos[i]:self.fullnameIntsPos[i]+j]
            hex_str = hex_num.hex()     #转16进制
            self.fullnameInts[i] = int(hex_str, 16) - oldnamelen
    
    #展示人物卡
    def show_image(self):
        if self.picbytes is not None:
            img = Image.open(BytesIO(self.picbytes))
            img.show()
        else:
            print("还没有加载人物卡")
            
    def get_image_bytes(self):
        if self.picbytes is not None:
            return self.picbytes
        else:
            print("还没有加载人物卡")
            
    #保存人物卡
    def save_card(self, save_path):
        filebytes = self.picbytes + self.databytes
        with open(save_path, 'wb') as file:
            file.write(filebytes)
            
    def save_name_ints(self, namelen):
        for i in range(8):
            # 获取新的int值
            newlen = self.fullnameInts[i] + namelen
            # 转换为16进制字节
            td = struct.pack('i', newlen)

            if i == 5 or i == 7:
                # 只有一个字节
                data = bytes([td[0]])
                self.update_change_to_databytes(data, self.fullnameIntsPos[i])
            else:
                data = bytes([td[1], td[0]])
                self.update_change_to_databytes(data, self.fullnameIntsPos[i])
                
    def update_change_to_databytes(self, contentbytes, pos, end=""):
        valid_ends = ["", "1byte", "0", "1", "2", "3"]
        if end.lower() in valid_ends:
            contentlength = len(contentbytes)
        else:
            curstring = ""
            postemp = pos + 1
            while curstring != end.lower():
                current = self.databytes[postemp:postemp + 1]
                curstring = ''.join(format(x, '02x') for x in current).lower()
                if curstring != end.lower():
                    postemp += 1
                else:
                    break
            contentlength = postemp - pos
            
        before = self.databytes[:pos]
        after = self.databytes[pos + contentlength:]

        combined = bytearray()
        combined.extend(before)
        combined.extend(contentbytes)
        combined.extend(after)
        self.databytes = combined
        
    def update_all(self):
        for key in self.data:
            self.data[key].load_data(self.databytes)

    



