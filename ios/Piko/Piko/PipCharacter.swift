import SwiftUI
extension Color {init(rgb:Int){self.init(red:Double((rgb>>16)&255)/255,green:Double((rgb>>8)&255)/255,blue:Double(rgb&255)/255)}}

struct PipCharacter:View {
    var rig=0
    var tint:Int=0
    var state="idle"
    var expression:PipExpression?=nil
    var paused=false
    var frames:[UIImage]?=nil
    @Environment(\.accessibilityReduceMotion) private var reduced
    @Environment(\.scenePhase) private var phase
    @State private var started=Date()
    private func sprite(_ frame:Int)->Image {
        if let frames,frames.indices.contains(frame){return Image(uiImage:frames[frame])}
        if rig<PixelLibrary.characters.count{return Image("Pixel\(max(0,rig))_\(frame)")}
        return Image(systemName:"sparkles")
    }
    var body:some View {
        let pose=expression ?? .named(state)
        let motion=expression.map(PixelLibrary.motion) ?? state
        TimelineView(.animation(minimumInterval:1/30,paused:paused || reduced || phase != .active)){timeline in
            let time=reduced ? 0:timeline.date.timeIntervalSince(started)*Double(pose.speed)
            let frame=PixelLibrary.frame(motion,time:time)
            sprite(frame).resizable()
                .interpolation(.none).scaledToFit()
                .hueRotation(.degrees(PixelLibrary.hue(rig:rig,tint:tint)))
                .overlay {if motion=="dizzy" {DizzySpiralEyes(eyes:DizzyEyeLocator.eyes(rig:rig,frames:frames),time:time);DizzyStars(time:time)}}
                .rotationEffect(.radians(Double(pose.tilt)*(reduced ? 0:0.6)+(motion=="dizzy" && !reduced ? sin(time*4)*0.15:0)))
                .offset(x:CGFloat(pose.gazeX)*3,y:CGFloat(-pose.gazeY)*3+(reduced ? 0:CGFloat(sin(time*2.2)*Double(pose.bounce)*24)))
                .padding(6)
        }.onChange(of:motion){_,_ in started=Date()}
         .accessibilityLabel("\(PixelLibrary.characters.map(\.name)[min(PixelLibrary.characters.count-1,max(0,rig))]), \(pose.name)")
    }
}
private struct DizzyStars:View {
    var time:Double
    var body:some View {
        GeometryReader {geo in
            let side=min(geo.size.width,geo.size.height)
            ForEach(0..<3){i in
                let angle=time*3.4+Double(i)*2.0943951
                Image(systemName:"star.fill").font(.system(size:max(6,side*0.055)))
                    .foregroundStyle(.yellow)
                    .position(x:geo.size.width/2+cos(angle)*side*0.17,y:(geo.size.height-side)/2+side*0.12+sin(angle)*side*0.045)
            }
        }.allowsHitTesting(false).accessibilityHidden(true)
    }
}
// Shared frame timing and pose IDs: firmware and browser consume the same catalog.
enum PixelLibrary {
    struct Key:Decodable {var pose:Int;var ms:Int}
    struct Character:Decodable {var id:Int;var name:String;var hue:Double;var dizzyEyes:[[Double]]}
    struct Catalog:Decodable {var motions:[String:[Key]];var characters:[Character]}
    static let catalog:Catalog = {
        guard let url=Bundle.main.url(forResource:"PipMotions",withExtension:"json"),let data=try? Data(contentsOf:url),let c=try? JSONDecoder().decode(Catalog.self,from:data) else{return .init(motions:[:],characters:[.init(id:0,name:"Pip",hue:148,dizzyEyes:[[37,39,5.5,7.5],[58,39,5.5,7.5]])])}
        return c
    }()
    static var motions:[String:[Key]]{catalog.motions}
    static var characters:[Character]{catalog.characters}
    static func frame(_ name:String,time:Double)->Int {
        let frames=motions[name] ?? motions["idle"] ?? [.init(pose:0,ms:1000)]
        let duration=frames.reduce(0){$0+$1.ms};var position=Int(max(0,time)*1000)%max(1,duration)
        for f in frames {if position<f.ms{return f.pose};position-=f.ms};return frames[0].pose
    }
    static func motion(_ p:PipExpression)->String {
        // A named preset uses its authored sequence. Generated poses compose the
        // nearest authored expression with continuous tilt, gaze, bounce and tempo.
        if motions[p.motion] != nil {return p.motion}
        if motions[p.id] != nil {return p.id}
        if p.armWave>0.25 || p.rightArm>1.9{return "wave"}
        if p.mouthPulse>0.3{return "speaking"}
        if abs(p.wink)>0.4{return "wink"}
        if p.brow>0.5 && p.smile<0{return "angry"}
        if p.eyeOpen<0.16{return "sleeping"}
        if p.smile < -0.45{return "sad"}
        if p.eyeOpen>1.25 && p.mouthOpen>0.4{return "surprised"}
        if p.smile>0.8 || p.leftArm>1.7 && p.rightArm>1.7{return "happy"}
        if p.leftArm>1.1 || abs(p.gazeX)>0.4{return "thinking"}
        if p.mouthOpen>0.25{return "speaking"}
        if p.eyeOpen>1.05{return "listening"}
        return "idle"
    }
    static func hue(rig:Int,tint:Int)->Double {
        guard tint != 0 else{return 0}
        let target=UIColor(red:CGFloat((tint>>16)&255)/255,green:CGFloat((tint>>8)&255)/255,blue:CGFloat(tint&255)/255,alpha:1)
        var h:CGFloat=0;target.getHue(&h,saturation:nil,brightness:nil,alpha:nil)
        return Double(h*360)-characters.map(\.hue)[min(PixelLibrary.characters.count-1,max(0,rig))]
    }
}
struct DeviceIllustration:View {
    var rig=0
    var shape="round"
    var size:CGFloat=210
    var body:some View {WappaiDevice3D(hardware:shape=="rectangle" ? .rectangle18:shape=="square" ? .square216:.round175c).frame(width:size,height:size)}
}
