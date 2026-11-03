import Foundation
func expect(_ condition:Bool,_ label:String){if !condition{fatalError(label)}}
let order=["1.0.0-alpha","1.0.0-alpha.1","1.0.0-alpha.beta","1.0.0-beta","1.0.0-beta.2","1.0.0-beta.11","1.0.0-rc.1","1.0.0","1.0.1","2.0.0"]
for (a,b) in zip(order,order.dropFirst()){expect(FirmwareVersion(a)! < FirmwareVersion(b)!,a+" < "+b)}
expect(FirmwareVersion("1.0.0-dev.10")! > FirmwareVersion("1.0.0-dev.2")!,"numeric dev comparison")
expect(FirmwareVersion("v1.0.0+build.1")==FirmwareVersion("1.0.0+build.2"),"metadata ignored")
for bad in ["QA","1.0","1.0.0-dev.01","01.0.0","1.0.0-","99999999999999999999999999.1.1"]{expect(FirmwareVersion(bad)==nil,"reject "+bad)}
let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))
let catalog=try JSONDecoder().decode(FirmwareCatalog.self,from:data)
let supported=catalog.board("ws-s3-175c")!
expect(supported.status=="available" && supported.release!.isValid,"published release valid")
for id in ["ws-s3-175","ws-s3-18","ws-s3-216"] {let board=catalog.board(id)!;expect(board.status=="unvalidated" && board.release==nil,"block untested "+id)}
expect(catalog.board("unknown")==nil,"no chip-family fallback")
for bad in ["http://github.com/rotem221/Wappai/releases/tag/v1","https://github.com.evil.test/rotem221/Wappai/releases/tag/v1","https://github.com/other/repo/releases/tag/v1"] {expect(FirmwareRelease.allowedURL(bad,host:"github.com",pathPrefix:"/rotem221/Wappai/releases/tag/")==nil,"reject foreign URL")}
print("Firmware policy: SemVer, catalog, exact board matching and URL checks passed")
