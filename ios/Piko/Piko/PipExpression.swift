import Foundation

// Versioned, bounded pose data, never executable model output.
struct PipExpression:Codable,Identifiable,Equatable {
    var id:String="preview"
    var name:String="הבעה חדשה"
    var motion:String=""
    var eyeOpen:Float=1
    var smile:Float=0.6
    var mouthOpen:Float=0
    var gazeX:Float=0
    var gazeY:Float=0
    var tilt:Float=0
    var leftArm:Float=0
    var rightArm:Float=0
    var bounce:Float=0.04
    var speed:Float=1
    var cue:String="soft"
    var wink:Float=0
    var brow:Float=0
    var mouthPulse:Float=0
    var armWave:Float=0
    private static let basePresets:[PipExpression]=[
        .init(id:"idle",name:"רגוע",cue:"none"),
        .init(id:"happy",name:"שמחה",eyeOpen:0.22,smile:1,leftArm:0.7,rightArm:0.8,bounce:0.13,speed:1.4,cue:"joy"),
        .init(id:"thinking",name:"מחשבה",eyeOpen:0.72,smile:-0.2,gazeX:-0.5,gazeY:0.5,tilt:0.12,leftArm:1.5,bounce:0.015,speed:0.65,cue:"think"),
        .init(id:"curious",name:"סקרנות",eyeOpen:1.2,smile:0.1,mouthOpen:0.3,gazeX:0.3,tilt:-0.16,rightArm:0.6,cue:"curious"),
        .init(id:"excited",name:"התרגשות",eyeOpen:0.25,smile:1,mouthOpen:0.8,leftArm:1.8,rightArm:1.8,bounce:0.2,speed:1.8,cue:"joy"),
        .init(id:"sad",name:"עצב",eyeOpen:0.65,smile:-0.8,gazeY:-0.4,tilt:0.08,bounce:0.01,speed:0.5,cue:"soft"),
        .init(id:"surprised",name:"הפתעה",eyeOpen:1.35,smile:0,mouthOpen:0.7,leftArm:0.45,rightArm:0.45,bounce:0.08,cue:"curious"),
        .init(id:"sleeping",name:"שינה",eyeOpen:0.05,smile:0.2,tilt:0.08,bounce:0.015,speed:0.35,cue:"none"),
        .init(id:"listening",name:"הקשבה",eyeOpen:1.1,smile:0.3,gazeY:0.2,tilt:-0.08,leftArm:0.3,bounce:0.025,cue:"none"),
        .init(id:"speaking",name:"דיבור",smile:0.6,mouthOpen:0.45,rightArm:0.55,bounce:0.05,cue:"none"),
        .init(id:"love",name:"אהבה",eyeOpen:0.3,smile:0.9,leftArm:1.2,rightArm:1.2,bounce:0.06,speed:0.8,cue:"soft"),
        .init(id:"wave",name:"שלום",smile:0.8,rightArm:2.2,bounce:0.06,speed:1.5,cue:"hello"),
        .init(id:"proud",name:"גאווה",eyeOpen:0.8,smile:0.8,gazeY:0.3,leftArm:0.7,rightArm:0.7,bounce:0.03,cue:"joy"),
        .init(id:"confused",name:"בלבול",eyeOpen:0.65,smile:-0.3,gazeX:0.6,tilt:0.22,rightArm:1.1,cue:"curious"),
        .init(id:"shy",name:"ביישנות",eyeOpen:0.6,smile:0.5,gazeX:-0.6,gazeY:-0.3,tilt:-0.12,leftArm:1,rightArm:1,cue:"soft"),
        .init(id:"angry",name:"כעס",eyeOpen:0.45,smile:-0.7,tilt:-0.06,leftArm:0.4,rightArm:0.4,bounce:0.025,speed:1.8,cue:"none"),
        .init(id:"joy",name:"אושר",eyeOpen:0.2,smile:1,mouthOpen:0.65,leftArm:1.5,rightArm:1.5,bounce:0.15,speed:1.4,cue:"joy"),
        .init(id:"starstruck",name:"התפעלות",eyeOpen:1.4,smile:0.9,mouthOpen:0.35,leftArm:0.6,rightArm:0.6,bounce:0.08,cue:"curious"),
        .init(id:"shocked",name:"תדהמה",eyeOpen:1.4,smile:0,mouthOpen:1,tilt:-0.12,leftArm:1.6,rightArm:1.6,bounce:0.04,cue:"curious"),
        .init(id:"scared",name:"פחד",eyeOpen:1.3,smile:-0.7,mouthOpen:0.4,tilt:0.1,leftArm:1.2,rightArm:1.2,bounce:0.015,speed:2,cue:"soft"),
        .init(id:"nervous",name:"התרגשות שקטה",eyeOpen:0.8,smile:0.1,gazeX:-0.5,tilt:0.08,leftArm:1.1,bounce:0.025,speed:1.8,cue:"soft"),
        .init(id:"crying",name:"דמעות",eyeOpen:0.15,smile:-1,mouthOpen:0.5,gazeY:-0.5,leftArm:1.5,rightArm:1.5,bounce:0.03,speed:0.6,cue:"soft"),
        .init(id:"furious",name:"זעם",eyeOpen:0.35,smile:-1,tilt:-0.12,leftArm:0.9,rightArm:0.9,bounce:0.03,speed:2,cue:"none"),
        .init(id:"annoyed",name:"חוסר סבלנות",eyeOpen:0.4,smile:-0.4,gazeX:0.7,tilt:0.12,rightArm:0.5,bounce:0.01,cue:"none"),
        .init(id:"skeptical",name:"ספקנות",eyeOpen:0.6,smile:-0.1,gazeX:-0.6,tilt:0.2,leftArm:1.4,bounce:0.015,cue:"curious"),
        .init(id:"bored",name:"שעמום",eyeOpen:0.3,smile:0,gazeY:-0.4,tilt:0.15,bounce:0.01,speed:0.4,cue:"none"),
        .init(id:"sleepy",name:"נמנום",eyeOpen:0.25,smile:0.2,gazeY:-0.2,tilt:0.16,bounce:0.015,speed:0.4,cue:"none"),
        .init(id:"dizzy",name:"סחרחורת",eyeOpen:0.65,smile:0,mouthOpen:0.35,gazeX:0.6,tilt:0.25,leftArm:1.3,rightArm:0.6,bounce:0.03,speed:0.8,cue:"none"),
        .init(id:"wink",name:"קריצה",eyeOpen:1,smile:0.8,tilt:-0.1,rightArm:0.7,bounce:0.05,cue:"hello"),
        .init(id:"mischievous",name:"שובבות",eyeOpen:0.65,smile:1,gazeX:0.6,tilt:-0.18,leftArm:0.8,rightArm:0.3,bounce:0.09,speed:1.5,cue:"joy"),
        .init(id:"kiss",name:"נשיקה",eyeOpen:0.12,smile:0,mouthOpen:0.25,leftArm:1.3,rightArm:1.3,bounce:0.025,cue:"soft"),
        .init(id:"singing",name:"שירה",eyeOpen:0.2,smile:1,mouthOpen:0.7,tilt:-0.08,leftArm:0.6,rightArm:1.4,bounce:0.09,speed:1.3,cue:"joy"),
        .init(id:"relieved",name:"הקלה",eyeOpen:0.25,smile:0.8,leftArm:0.3,rightArm:0.3,bounce:0.02,speed:0.5,cue:"soft"),
        .init(id:"determined",name:"נחישות",eyeOpen:0.7,smile:0.3,gazeY:0.2,leftArm:0.8,rightArm:0.8,bounce:0.035,cue:"none"),
        .init(id:"working",name:"ריכוז",eyeOpen:0.75,smile:0,gazeY:-0.3,tilt:0.04,leftArm:0.5,rightArm:0.5,bounce:0.02,speed:0.6,cue:"think"),
        .init(id:"success",name:"הצלחה",eyeOpen:0.2,smile:1,mouthOpen:0.45,leftArm:2,rightArm:2,bounce:0.15,speed:1.4,cue:"joy"),
        .init(id:"error",name:"אופס",eyeOpen:1.2,smile:-0.6,mouthOpen:0.3,tilt:0.18,rightArm:1.4,bounce:0.02,cue:"soft"),
        .init(id:"disconnected",name:"ממתין לחיבור",eyeOpen:0.7,smile:0,gazeX:0.6,tilt:0.1,bounce:0.015,speed:0.5,cue:"none"),
        .init(id:"low_battery",name:"סוללה חלשה",eyeOpen:0.3,smile:-0.2,gazeY:-0.6,tilt:0.15,bounce:0.01,speed:0.3,cue:"none"),
        .init(id:"yawn",name:"פיהוק",eyeOpen:0.1,smile:0,mouthOpen:0.85,leftArm:1.4,bounce:0.015,speed:0.4,cue:"none")
    ]
    static let presets:[PipExpression]=basePresets.map { (source:PipExpression) -> PipExpression in
        var p=source
        p.motion=p.id
        if p.id=="wink"{p.wink=1}
        if ["angry","furious","determined"].contains(p.id){p.brow=0.8}
        if ["sad","crying","scared"].contains(p.id){p.brow = -0.6}
        if ["speaking","singing"].contains(p.id){p.mouthPulse=1}
        if p.id=="wave"{p.armWave=1}
        return p
    }
    static func named(_ state:String)->Self {presets.first{$0.id==state} ?? presets[0]}
}

// Saved v1 poses remain readable when new optional controls are introduced.
extension PipExpression {
    enum CodingKeys:String,CodingKey {case id,name,motion,eyeOpen,smile,mouthOpen,gazeX,gazeY,tilt,leftArm,rightArm,bounce,speed,cue,wink,brow,mouthPulse,armWave}
    init(from decoder:Decoder)throws {
        self.init()
        let c=try decoder.container(keyedBy:CodingKeys.self)
        id=try c.decodeIfPresent(String.self,forKey:.id) ?? id
        name=try c.decodeIfPresent(String.self,forKey:.name) ?? name
        motion=try c.decodeIfPresent(String.self,forKey:.motion) ?? motion
        cue=try c.decodeIfPresent(String.self,forKey:.cue) ?? cue
        eyeOpen=try c.decodeIfPresent(Float.self,forKey:.eyeOpen) ?? eyeOpen
        smile=try c.decodeIfPresent(Float.self,forKey:.smile) ?? smile
        mouthOpen=try c.decodeIfPresent(Float.self,forKey:.mouthOpen) ?? mouthOpen
        gazeX=try c.decodeIfPresent(Float.self,forKey:.gazeX) ?? gazeX
        gazeY=try c.decodeIfPresent(Float.self,forKey:.gazeY) ?? gazeY
        tilt=try c.decodeIfPresent(Float.self,forKey:.tilt) ?? tilt
        leftArm=try c.decodeIfPresent(Float.self,forKey:.leftArm) ?? leftArm
        rightArm=try c.decodeIfPresent(Float.self,forKey:.rightArm) ?? rightArm
        bounce=try c.decodeIfPresent(Float.self,forKey:.bounce) ?? bounce
        speed=try c.decodeIfPresent(Float.self,forKey:.speed) ?? speed
        wink=try c.decodeIfPresent(Float.self,forKey:.wink) ?? wink
        brow=try c.decodeIfPresent(Float.self,forKey:.brow) ?? brow
        mouthPulse=try c.decodeIfPresent(Float.self,forKey:.mouthPulse) ?? mouthPulse
        armWave=try c.decodeIfPresent(Float.self,forKey:.armWave) ?? armWave
    }
}
