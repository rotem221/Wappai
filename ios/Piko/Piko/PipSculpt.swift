// Wappai clay collection. Shared geometry: RealityKit on iOS, offline raster bake for ESP32.
// Coordinates are metres in the renderer's local model space; no runtime network assets.
import Foundation
import simd

struct PipMesh {
    var vertices:[SIMD3<Float>]=[]
    var normals:[SIMD3<Float>]=[]
    var triangles:[UInt32]=[]
    static func surface(rows:Int=64,columns:Int=72,_ point:(Float,Float)->SIMD3<Float>)->PipMesh {
        var m=PipMesh()
        for i in 0...rows {for j in 0...columns {
            let u=Float(i)/Float(rows),v=Float(j)/Float(columns)
            let p=point(u,v),du=point(min(0.99999,u+0.0001),v)-point(max(0.00001,u-0.0001),v)
            let dv=point(u,v+0.0001)-point(u,v-0.0001)
            let n=simd_cross(du,dv)
            m.vertices.append(p);m.normals.append(simd_length(n)>0.000000000001 ? simd_normalize(n):SIMD3<Float>(0,u<0.5 ? -1:1,0))
            if i<rows && j<columns {let a=UInt32(i*(columns+1)+j),b=a+UInt32(columns+1);m.triangles += [a,b,a+1,a+1,b,b+1]}
        }}
        return m
    }
    static func ellipsoid(_ radius:SIMD3<Float>)->PipMesh {
        surface(rows:40,columns:48){u,v in let p = Float.pi*u,a=2*Float.pi*v;return SIMD3<Float>(sin(p)*cos(a),-cos(p),sin(p)*sin(a))*radius}
    }
    // Catmull–Rom loft, giving Pip a continuous curled silhouette instead of overlapping circles.
    static func loft(_ sections:[SIMD4<Float>])->PipMesh {
        surface {u,v in
            let f=u*Float(sections.count-1),i=min(sections.count-2,Int(f)),t=f-Float(i)
            let p0=sections[max(0,i-1)],p1=sections[i],p2=sections[i+1],p3=sections[min(sections.count-1,i+2)]
            let s=(2*p1 + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t*t + (-p0+3*p1-3*p2+p3)*t*t*t)*0.5
            let a=v*2*Float.pi
            return [s.x+max(0.001,s.z)*cos(a),s.y,max(0.001,s.w)*sin(a)]
        }
    }
    static func tube(_ points:[SIMD3<Float>],radius:Float)->PipMesh {
        var result=surface(rows:points.count-1,columns:12){u,v in
            let f=u*Float(points.count-1),i=min(points.count-2,Int(f)),t=f-Float(i)
            let p=simd_mix(points[i],points[i+1],SIMD3(repeating:t)),d=simd_normalize(points[i+1]-points[i])
            let a=simd_normalize(simd_cross(d,SIMD3<Float>(0,0,1))),b=simd_cross(d,a),angle=v*2*Float.pi
            return p+radius*(a*cos(angle)+b*sin(angle))
        }
        for end in [points.first!,points.last!] {
            let cap=ellipsoid([radius,radius,radius]),offset=UInt32(result.vertices.count)
            result.vertices += cap.vertices.map{$0+end};result.normals += cap.normals;result.triangles += cap.triangles.map{$0+offset}
        }
        return result
    }
}
struct PipPart {
    var name:String;var mesh:PipMesh;var position:SIMD3<Float> = .zero
    var rotation:Float=0;var color:Int;var roughness:Float=0.72
}
enum PipSculpt {
    static let palette=[0x69E8BC,0xFFAF80,0x84C5F1]
    static func parts(rig:Int,tint:Int=0,face:Bool=true)->[PipPart] {
        let c=tint==0 ? palette[min(2,max(0,rig))]:tint
        var p:[PipPart]=[]
        func oval(_ name:String,_ r:SIMD3<Float>,_ pos:SIMD3<Float>,_ color:Int,_ rotation:Float=0){p.append(.init(name:name,mesh:.ellipsoid(r),position:pos,rotation:rotation,color:color))}
        if rig==1 {
            // Tail is behind the torso, with a cream dipped tip.
            p.append(.init(name:"tail",mesh:.loft([[0,-0.65,0.02,0.02],[0.3,-0.5,0.25,0.23],[0.57,-0.15,0.24,0.22],[0.65,0.16,0.17,0.17],[0.57,0.39,0.001,0.001]]),position:[0.6,-0.02,-0.28],color:c))
            oval("tailTip",[0.17,0.26,0.16],[1.23,0.17,-0.24],0xFFE8CB,-0.2)
            for side:Float in [-1,1] {
                let ear=PipMesh.loft([[0,0,0.25,0.18],[side*0.03,0.22,0.24,0.15],[side*0.03,0.48,0.16,0.10],[0,0.64,0.001,0.001]])
                p.append(.init(name:"ear\(side)",mesh:ear,position:[side*0.60,0.67,-0.05],rotation:side * -0.16,color:c))
                p.append(.init(name:"earInner\(side)",mesh:.loft([[0,0,0.13,0.025],[side*0.02,0.18,0.12,0.026],[0,0.40,0.001,0.001]]),position:[side*0.60,0.81,0.12],rotation:side * -0.16,color:0xFFE9CC))
            }
        }
        let torso:PipMesh
        if rig==0 {torso = .loft([[0,-0.90,0.001,0.001],[0,-0.84,0.64,0.45],[0,-0.58,0.94,0.67],[0,-0.12,1.02,0.77],[0,0.35,0.88,0.71],[0.04,0.75,0.63,0.53],[0.21,1.02,0.37,0.34],[0.43,1.22,0.23,0.21],[0.46,1.43,0.12,0.11],[0.30,1.59,0.001,0.001]])}
        else {torso = .loft([[0,-0.91,0.001,0.001],[0,-0.84,0.64,0.44],[0,-0.64,0.89,0.62],[0,-0.22,0.98,0.72],[0,0.23,0.96,0.71],[0,0.63,0.78,0.59],[0,0.88,0.48,0.36],[0,0.97,0.001,0.001]])}
        p.append(.init(name:"torso",mesh:torso,color:c))
        for side:Float in [-1,1] {
            oval(side<0 ? "leftFoot":"rightFoot",[0.26,0.15,0.32],[side*0.48,-0.91,0.12],c)
            oval(side<0 ? "leftArm":"rightArm",[0.22,0.39,0.25],[side*0.92,-0.17,0.27],c,side*0.5)
        }
        if rig==1 {
            // Soft cream cheek patches sit on the curved muzzle, not on a flat square plane.
            oval("cheekL",[0.31,0.20,0.06],[-0.65,0.02,0.566],0xFFE6C4,-0.38)
            oval("cheekR",[0.31,0.20,0.06],[0.65,0.02,0.566],0xFFE6C4,0.38)
        }
        if rig==2 {oval("visor",[0.77,0.43,0.18],[0,0.28,0.59],0x123C4C)}
        if face {
            let ink=rig==2 ? 0xD9F8FF:0x083B37
            for side:Float in [-1,1] {
                let eye=PipMesh.loft([[0,-0.195,0.001,0.001],[0,-0.178,0.055,0.018],[0,-0.14,0.09,0.026],[0,-0.08,0.095,0.028],[0,0.08,0.095,0.028],[0,0.14,0.09,0.026],[0,0.178,0.055,0.018],[0,0.195,0.001,0.001]])
                p.append(.init(name:side<0 ? "eyeL":"eyeR",mesh:eye,position:[side*0.32,rig==2 ? 0.33:0.22,rig==2 ? 0.785:0.728],color:ink))
            }
            let points=(0...24).map{i -> SIMD3<Float> in let x=Float(i)/24*0.34-0.17;return [x,-0.13+2.7*x*x,0.81]}
            p.append(.init(name:"mouth",mesh:.tube(points,radius:0.035),position:[0,rig==2 ? 0.20:0,0],color:ink))
        }
        return p
    }
}
