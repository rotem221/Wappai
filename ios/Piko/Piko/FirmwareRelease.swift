import Foundation

struct FirmwareCatalog: Decodable {
    let schema_version: Int
    let repository: String
    let boards: [FirmwareBoard]
    func board(_ id: String) -> FirmwareBoard? {
        guard schema_version == 1, repository == "rotem221/Wappai",
              Set(boards.map(\.id)).count == boards.count else { return nil }
        return boards.first { $0.id == id }
    }
}
struct FirmwareBoard: Decodable {
    let id: String
    let name: String
    let status: String
    let release: FirmwareRelease?
}
struct FirmwareRelease: Decodable, Identifiable {
    let version: String
    let package_version: String
    let channel: String
    let release_url: String
    let install_url: String
    let update_method: String
    let sha256: String
    let bytes: Int
    var id: String { package_version }
    var releaseURL: URL? { Self.allowedURL(release_url, host:"github.com", pathPrefix:"/rotem221/Wappai/releases/tag/") }
    var installURL: URL? { Self.allowedURL(install_url, host:"wappai-companion.rotem221.chatgpt.site", pathPrefix:"/flash.html") }
    var isValid: Bool {
        FirmwareVersion(version) != nil && ["stable","development"].contains(channel) && update_method == "usb" &&
        sha256.range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil && (24...16_777_216).contains(bytes) &&
        releaseURL != nil && installURL != nil
    }
    static func allowedURL(_ text:String, host:String, pathPrefix:String) -> URL? {
        guard let url=URL(string:text),url.scheme=="https",url.host==host,url.user==nil,url.password==nil,
              url.port==nil,url.path.hasPrefix(pathPrefix),url.fragment==nil else{return nil}
        if host.hasSuffix("chatgpt.site") && url.path != "/flash.html" {return nil}
        return url
    }
}
// SemVer precedence, including numeric prerelease components (dev.10 > dev.2).
struct FirmwareVersion: Comparable {
    let core:[Int]
    let pre:[String]
    init?(_ value:String) {
        let text=value.hasPrefix("v") ? String(value.dropFirst()):value
        guard text.range(of:"^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?(\\+[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$",options:.regularExpression) != nil else{return nil}
        let clean=text.split(separator:"+",maxSplits:1)[0].split(separator:"-",maxSplits:1)
        let numbers=clean[0].split(separator:".").compactMap{Int($0)}
        guard numbers.count==3 else{return nil};core=numbers
        pre=clean.count==2 ? clean[1].split(separator:".").map(String.init):[]
        guard !pre.contains(where:{$0.count>1 && $0.first=="0" && $0.allSatisfy(\.isNumber)}) else{return nil}
    }
    static func < (a:Self,b:Self)->Bool {
        if a.core != b.core{return a.core.lexicographicallyPrecedes(b.core)}
        if a.pre.isEmpty{return false};if b.pre.isEmpty{return true}
        for (x,y) in zip(a.pre,b.pre) where x != y {
            let xn=x.allSatisfy(\.isNumber),yn=y.allSatisfy(\.isNumber)
            if xn && yn {return x.count == y.count ? x<y:x.count<y.count}
            if xn != yn{return xn};return x<y
        }
        return a.pre.count<b.pre.count
    }
}
