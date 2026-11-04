// Package approved imagegen artwork at platform sizes; preserve source masters.
// Run from repository root: swift tools/wappai/prepare_brand.swift
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
let root=URL(fileURLWithPath:FileManager.default.currentDirectoryPath)
func load(_ file:String)->CGImage {
    let source=CGImageSourceCreateWithURL(root.appendingPathComponent(file) as CFURL,nil)!
    return CGImageSourceCreateImageAtIndex(source,0,nil)!
}
func trim(_ image:CGImage)->CGImage {
    let w=image.width,h=image.height
    let c=CGContext(data:nil,width:w,height:h,bitsPerComponent:8,bytesPerRow:w*4,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.draw(image,in:CGRect(x:0,y:0,width:w,height:h))
    let p=c.data!.assumingMemoryBound(to:UInt8.self)
    var x0=w,y0=h,x1=0,y1=0
    for y in 0..<h {for x in 0..<w {if p[(y*w+x)*4+3]>32 {x0=min(x0,x);x1=max(x1,x);y0=min(y0,y);y1=max(y1,y)}}}
    let pad=8;x0=max(0,x0-pad);y0=max(0,y0-pad);x1=min(w-1,x1+pad);y1=min(h-1,y1+pad)
    return image.cropping(to:CGRect(x:x0,y:y0,width:x1-x0+1,height:y1-y0+1))!
}
func save(_ image:CGImage,_ path:String,_ width:Int,_ height:Int,opaque:Bool=false) {
    let c=CGContext(data:nil,width:width,height:height,bitsPerComponent:8,bytesPerRow:0,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:(opaque ? CGImageAlphaInfo.noneSkipLast:CGImageAlphaInfo.premultipliedLast).rawValue)!
    c.interpolationQuality = .none
    c.draw(image,in:CGRect(x:0,y:0,width:width,height:height))
    let url=root.appendingPathComponent(path)
    try! FileManager.default.createDirectory(at:url.deletingLastPathComponent(),withIntermediateDirectories:true)
    let out=CGImageDestinationCreateWithURL(url as CFURL,UTType.png.identifier as CFString,1,nil)!
    CGImageDestinationAddImage(out,c.makeImage()!,nil);precondition(CGImageDestinationFinalize(out))
}
let symbol=load("assets/brand/pixel-source/symbol.png")
let screenSymbol=load("assets/brand/pixel-source/screen-symbol.png")
let logo=trim(load("assets/brand/pixel-source/wordmark.png"))
let app=load("assets/brand/pixel-source/app-icon.png")
let height=Int((Double(logo.height)*1500/Double(logo.width)).rounded())
for path in ["assets/brand/wappai-symbol.png","ios/Piko/Piko/Assets.xcassets/WappaiMark.imageset/mark.png","server/sim/wappai-symbol.png"] {save(symbol,path,512,512)}
for path in ["assets/brand/wappai-screen-mark.png","ios/Piko/Piko/Assets.xcassets/WappaiScreenMark.imageset/mark.png","server/sim/wappai-screen-mark.png"] {save(screenSymbol,path,512,512)}
for path in ["assets/brand/wappai-wordmark.png","ios/Piko/Piko/Assets.xcassets/WappaiWordmark.imageset/wordmark.png","server/sim/wappai-wordmark.png"] {save(logo,path,1500,height)}
for path in ["assets/brand/wappai-master.png","ios/Piko/Piko/Assets.xcassets/AppIcon.appiconset/icon.png"] {save(app,path,1024,1024,opaque:true)}
save(app,"server/sim/wappai-mark.png",256,256,opaque:true)
save(logo,"assets/brand/wappai-hub-wordmark.png",300,Int(Double(height)/5))
print("Packaged pixel brand: transparent symbol, \(1500)x\(height) wordmark, opaque 1024px iOS icon")
