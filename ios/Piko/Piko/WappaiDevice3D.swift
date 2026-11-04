import SwiftUI
import RealityKit
import simd

struct WappaiWordmark:View {
    @Environment(\.colorScheme) private var scheme
    var body:some View {
        Image("WappaiWordmark")
            .renderingMode(scheme == .dark ? .template:.original)
            .resizable().interpolation(.none).scaledToFit()
            .foregroundStyle(Color(red:0.78,green:1,blue:0.9))
            .accessibilityLabel("Wappai")
    }
}

// Dimensions and silhouette from Waveshare drawings in docs/wappai/hardware-reference.
// Local geometry keeps the turntable interactive and works without network access.
enum WappaiHardware:String,CaseIterable,Identifiable {
    case round175c, rectangle18, square216
    var id:String{rawValue}
    var title:String{switch self{case .round175c:"1.75C";case .rectangle18:"1.8";case .square216:"2.16"}}
    var size:SIMD3<Float>{switch self{case .round175c:[0.055,0.055,0.01505];case .rectangle18:[0.0376,0.0452,0.015];case .square216:[0.046,0.046,0.0225]}}
}
struct WappaiDevice3D:View {
    var hardware:WappaiHardware = .round175c
    var animated=true
    @Environment(\.accessibilityReduceMotion) private var reduced
    @Environment(\.scenePhase) private var phase
    @State private var started=Date()
    @State private var drag:Float=0
    @State private var previousDrag:Float=0
    var body:some View {
        TimelineView(.animation(minimumInterval:1/30,paused:!animated || reduced || phase != .active)){timeline in
            let seconds=timeline.date.timeIntervalSince(started)
            RealityView { content in
                content.camera = .virtual
                let device=DeviceModel.make(hardware);device.name="device";content.add(device)
                let camera=PerspectiveCamera();camera.camera.fieldOfViewInDegrees=30;camera.camera.near=0.001;camera.camera.far=1
                camera.look(at:.zero,from:[0,0,hardware == .round175c ? 0.127:0.113],relativeTo:nil);content.add(camera)
                for (position,intensity) in [(SIMD3<Float>(-0.08,0.10,0.12),Float(1800)),(SIMD3<Float>(0.10,0.03,0.05),Float(900)),(SIMD3<Float>(0,-0.08,-0.08),Float(1200))] {
                    let light=DirectionalLight();light.light.intensity=intensity
                    light.look(at:.zero,from:position,relativeTo:nil);content.add(light)
                }
            } update:{content in
                if let device=content.entities.first(where:{$0.name=="device"}) {
                    // A gentle display turn, then a full reveal, with the face visible most of the time.
                    let phase=Float(seconds.truncatingRemainder(dividingBy:16))
                    let turn=phase<10 ? sin(phase * .pi / 10)*0.48 : 2 * Float.pi * smooth((phase-10)/6)
                    let yaw:Float = !animated || reduced ? -0.18:turn+drag-0.18
                    device.orientation=simd_quatf(angle:yaw,axis:[0,1,0])*simd_quatf(angle:-0.12,axis:[1,0,0])
                }
            }
        }.gesture(DragGesture().onChanged{drag=previousDrag+Float($0.translation.width)*0.008}.onEnded{_ in previousDrag=drag})
         .accessibilityLabel("מכשיר Waveshare \(hardware.title) עם Wappai, תצוגה בתלת־ממד")
    }
    private func smooth(_ x:Float)->Float{x*x*(3-2*x)}
}
struct DeviceShowroom:View {
    @State private var hardware:WappaiHardware = .round175c
    init(hardware:WappaiHardware = .round175c){_hardware=State(initialValue:hardware)}
    var body:some View {
        VStack(spacing:24){
            Picker("דגם",selection:$hardware){ForEach(WappaiHardware.allCases){Text($0.title).tag($0)}}.pickerStyle(.segmented)
            WappaiDevice3D(hardware:hardware).id(hardware).frame(height:320)
            Text("Waveshare \(hardware.title)").font(.title2.bold())
            Text("סובב באצבע כדי לראות מכל צד").foregroundStyle(.secondary)
            Link("תמונות ומפרט היצרן",destination:URL(string:"https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-\(hardware.title)")!)
            Spacer()
        }.padding(24).navigationTitle("דגמי Wappai")
    }
}
@MainActor enum DeviceModel {
    static func material(_ color:UIColor,metal:Float=0,rough:Float=0.35)->PhysicallyBasedMaterial {
        var m=PhysicallyBasedMaterial();m.baseColor = .init(tint:color);m.metallic = .init(floatLiteral:metal);m.roughness = .init(floatLiteral:rough);return m
    }
    static func make(_ hardware:WappaiHardware)->Entity {
        let root=Entity(),s=hardware.size
        let metal=material(UIColor(white:0.72,alpha:1),metal:0.82,rough:0.27)
        let dark=material(UIColor(white:0.045,alpha:1),rough:0.30)
        let white=material(UIColor(white:0.86,alpha:1),rough:0.32)
        func box(_ name:String,_ size:SIMD3<Float>,_ position:SIMD3<Float>,_ m:PhysicallyBasedMaterial,_ radius:Float=0.001)->ModelEntity {
            let e=ModelEntity(mesh:roundedBox(size:size,radius:radius),materials:[m]);e.name=name;e.position=position;root.addChild(e);return e
        }
        if hardware == .round175c {
            let body=ModelEntity(mesh:roundShell(),materials:[metal]);root.addChild(body)
            let glass=ModelEntity(mesh:.generateCylinder(height:0.0008,radius:0.0241),materials:[dark]);glass.orientation=simd_quatf(angle:.pi/2,axis:[1,0,0]);glass.position.z=s.z/2;root.addChild(glass)
            let back=ModelEntity(mesh:.generateCylinder(height:0.0004,radius:0.0239),materials:[metal]);back.orientation=glass.orientation;back.position.z = -s.z/2;root.addChild(back)
            for (angle,label) in [(Float(-0.65),"BOOT"),(Float(0.65),"PWR")] {
                let button=box(label,[0.002,0.006,0.002],[cos(angle)*0.0269,sin(angle)*0.0269,0],metal,0.0008)
                button.orientation=simd_quatf(angle:angle,axis:[0,0,1])
            }
            let port=box("USB-C",[0.009,0.0018,0.0038],[0,-0.027,0],dark,0.0008)
            port.orientation=simd_quatf(angle:0.1,axis:[1,0,0])
            for y:Float in [-0.006,0,0.006] {_=box("microphone",[0.0012,0.0012,0.0012],[-0.027,y,0],dark,0.0005)}
        } else {
            _=box("case",s,.zero,hardware == .square216 ? white:dark,hardware == .square216 ? 0.0058:0.004)
            // A narrow polished bezel separates the glass from the softly rounded case.
            _=box("front rim",[s.x-0.0008,s.y-0.0008,0.0012],[0,0,s.z/2-0.0004],hardware == .square216 ? metal:material(UIColor(white:0.14,alpha:1),metal:0.45),0.0045)
            let front:SIMD3<Float>=[s.x-0.0038,s.y-0.0038,0.001]
            let glass=ModelEntity(mesh:.generatePlane(width:front.x,height:front.y,cornerRadius:0.005),materials:[UnlitMaterial(color:.black)])
            glass.position.z=s.z/2+0.0009;root.addChild(glass)
            if hardware == .rectangle18 {
                _=box("USB-C",[0.001,0.009,0.0035],[-s.x/2,-0.007,0],metal,0.001)
                _=box("USB-C interior",[0.0012,0.007,0.002],[-s.x/2-0.0001,-0.007,0],dark,0.0007)
                _=box("card slot",[0.001,0.006,0.001],[-s.x/2,0.007,0],metal,0.0003)
                for y:Float in [-0.012,0.012] {_=box("button",[0.0018,0.005,0.004],[s.x/2,y,0],dark,0.0008)}
            } else {
                _=box("USB-C",[0.008,0.0012,0.003],[0,-s.y/2,0.00265],dark,0.001)
                _=box("card slot",[0.001,0.012,0.0018],[-s.x/2,0,0.00295],dark,0.0004)
                for x:Float in [-0.010,0,0.010] {
                    let button=ModelEntity(mesh:.generateCylinder(height:0.0012,radius:0.00265),materials:[white]);button.position=[x,s.y/2,-0.00165];root.addChild(button)
                }
            }
            for x in [-s.x/2+0.0045,s.x/2-0.0045] {for y in [-s.y/2+0.0045,s.y/2-0.0045] {_=box("back screw",[0.002,0.002,0.0006],[x,y,-s.z/2],metal,0.0009)}}
        }
        if let image=UIImage(named:"WappaiScreenMark")?.cgImage,let texture=try? TextureResource.generate(from:image,options:.init(semantic:.color)) {
            var screen=UnlitMaterial();screen.color = .init(texture:.init(texture));screen.blending = .transparent(opacity:.init(floatLiteral:1))
            let logo=ModelEntity(mesh:.generatePlane(width:s.x*0.65,height:s.x*0.65),materials:[screen]);logo.position=[0,s.y*0.06,s.z/2+0.0018];root.addChild(logo)
        }
        let label=ModelEntity(mesh:.generateText("Wappai",extrusionDepth:0.00002,font:UIFont(descriptor:UIFont.systemFont(ofSize:0.0036,weight:.semibold).fontDescriptor.withDesign(.rounded)!,size:0.0036)),materials:[UnlitMaterial(color:.white)])
        let bounds=label.visualBounds(relativeTo:nil);label.position=[-bounds.extents.x/2,-s.y*0.20,s.z/2+0.0020];root.addChild(label)
        return root
    }
    // The standard box clamps its corner radius to the thin depth of a bezel.
    // Extrude a rounded outline instead so screen corners and rim agree.
    static func roundedBox(size:SIMD3<Float>,radius:Float)->MeshResource {
        let radius=min(radius,min(size.x,size.y)*0.49),bevel=min(0.0006,size.z*0.2)
        let rings:[SIMD2<Float>]=[[-size.z/2,bevel],[-size.z/2+bevel,0],[size.z/2-bevel,0],[size.z/2,bevel]]
        let count=68
        var points=[SIMD3<Float>](),normals=[SIMD3<Float>](),indices=[UInt32]()
        for (ring,level) in rings.enumerated(){
            for corner in 0..<4 {for step in 0...16 {
                let angle=Float(corner) * .pi/2+Float(step)/16 * .pi/2
                let sx:Float=corner==0 || corner==3 ? 1:-1,sy:Float=corner<2 ? 1:-1
                let radial=radius-level.y
                points.append([sx*(size.x/2-radius)+cos(angle)*radial,sy*(size.y/2-radius)+sin(angle)*radial,level.x])
                normals.append(simd_normalize(SIMD3<Float>(cos(angle),sin(angle),ring==0 ? -1:ring==3 ? 1:0)))
            }}
        }
        for ring in 0..<3 {for i in 0..<count {let a=UInt32(ring*count+i),b=UInt32(ring*count+(i+1)%count),c=a+UInt32(count),d=b+UInt32(count);indices += [a,b,c,b,d,c]}}
        for (ring,normal) in [(0,Float(-1)),(3,Float(1))] {
            let start=UInt32(points.count);points.append([0,0,rings[ring].x]);normals.append([0,0,normal])
            for i in 0..<count {points.append(points[ring*count+i]);normals.append([0,0,normal])}
            for i in 0..<count {let a=start+1+UInt32(i),b=start+1+UInt32((i+1)%count);indices += normal>0 ? [start,a,b]:[start,b,a]}
        }
        var d=MeshDescriptor();d.positions=MeshBuffers.Positions(points);d.normals=MeshBuffers.Normals(normals);d.primitives = .triangles(indices)
        return (try? MeshResource.generate(from:[d])) ?? .generateBox(size:size)
    }
    static func roundShell()->MeshResource {
        let profile:[SIMD2<Float>]=[[-0.007525,0.024],[-0.007,0.0254],[-0.0055,0.027],[-0.0035,0.0275],[0.0035,0.0275],[0.0055,0.0265],[0.007525,0.02448]]
        let segments=128
        var points=[SIMD3<Float>](),normals=[SIMD3<Float>](),indices=[UInt32]()
        for j in profile.indices {
            let before=profile[max(0,j-1)],after=profile[min(profile.count-1,j+1)]
            let dz=after.x-before.x,dr=after.y-before.y
            for i in 0...segments {
                let a=Float(i)/Float(segments)*2*Float.pi
                points.append([cos(a)*profile[j].y,sin(a)*profile[j].y,profile[j].x])
                normals.append(simd_normalize(SIMD3<Float>(cos(a)*dz,sin(a)*dz,-dr)))
                if j<profile.count-1 && i<segments {
                    let a=UInt32(j*(segments+1)+i),b=a+1,c=a+UInt32(segments+1),d=c+1
                    indices += [a,b,c,b,d,c]
                }
            }
        }
        var descriptor=MeshDescriptor(name:"Waveshare 1.75C silver enclosure")
        descriptor.positions=MeshBuffers.Positions(points);descriptor.normals=MeshBuffers.Normals(normals);descriptor.primitives = .triangles(indices)
        return (try? MeshResource.generate(from:[descriptor])) ?? .generateCylinder(height:0.01505,radius:0.0275)
    }
}
