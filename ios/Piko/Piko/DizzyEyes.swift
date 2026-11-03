import SwiftUI

struct DizzyEyeAnchor {
    var x: Double, y: Double, rx: Double, ry: Double
}

// Analyze uploaded art once, in its original 96px space. The binary pack uses
// the same component-pair algorithm, so old and new custom Pips need no migration.
enum DizzyEyeLocator {
    private final class Result: NSObject {
        let eyes: [DizzyEyeAnchor]
        init(_ eyes: [DizzyEyeAnchor]) { self.eyes = eyes }
    }
    private static let cache: NSCache<UIImage, Result> = {
        let cache = NSCache<UIImage, Result>(); cache.countLimit = 32; return cache
    }()
    static func eyes(rig: Int, frames: [UIImage]?) -> [DizzyEyeAnchor] {
        if let frames, frames.indices.contains(12) {
            let image = frames[12]
            if let cached = cache.object(forKey: image) { return cached.eyes }
            let result = locate(image)
            cache.setObject(Result(result), forKey: image)
            return result
        }
        let values = PixelLibrary.characters[min(max(0, rig), PixelLibrary.characters.count - 1)].dizzyEyes
        return values.map { DizzyEyeAnchor(x: $0[0], y: $0[1], rx: $0[2], ry: $0[3]) }
    }
    private struct Box { var l: Int, t: Int, r: Int, b: Int, area: Int }
    private static func locate(_ image: UIImage) -> [DizzyEyeAnchor] {
        var rgba = [UInt8](repeating: 0, count: 96 * 96 * 4)
        let rendered = rgba.withUnsafeMutableBytes { bytes -> Bool in
            guard let cg = image.cgImage,
                  let ctx = CGContext(data: bytes.baseAddress, width: 96, height: 96, bitsPerComponent: 8, bytesPerRow: 384, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            ctx.interpolationQuality = .none
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: 96, height: 96))
            return true
        }
        var l = 96, top = 96, r = 0, bottom = 0
        if rendered {
            for y in 0..<96 { for x in 0..<96 where rgba[(y * 96 + x) * 4 + 3] > 127 {
                l = min(l, x); r = max(r, x + 1); top = min(top, y); bottom = max(bottom, y + 1)
            }}
        }
        if l >= r || top >= bottom { l = 18; r = 78; top = 14; bottom = 90 }
        let width = Double(r - l), height = Double(bottom - top), center = Double(l + r) / 2
        let radius = max(4, min(8, width * 0.08))
        var result = [-1.0, 1.0].map { DizzyEyeAnchor(x: center + $0 * width * 0.16, y: Double(top) + height * 0.38, rx: radius, ry: radius * 1.3) }
        let left = l + Int(width * 0.10), right = r - Int(width * 0.10)
        let first = top + Int(height * 0.12), last = top + Int(height * 0.66)
        var best = -Double.infinity
        for bright in [false, true] {
            var seen = [Bool](repeating: false, count: 9216), boxes: [Box] = []
            func eligible(_ p: Int) -> Bool {
                guard rgba[p * 4 + 3] > 127 else { return false }
                // Quantize exactly as the RGB565 firmware pack does.
                let red = Int(rgba[p * 4]) / 8 * 255 / 31
                let green = Int(rgba[p * 4 + 1]) / 4 * 255 / 63
                let blue = Int(rgba[p * 4 + 2]) / 8 * 255 / 31
                return bright ? min(red, green, blue) >= 170 : max(red, green, blue) < 135 && max(red, green, blue) > 0
            }
            for y in first..<last { for x in left..<right {
                let at = y * 96 + x
                if seen[at] || !eligible(at) { continue }
                var box = Box(l: x, t: y, r: x + 1, b: y + 1, area: 0), stack = [at]
                seen[at] = true
                while let p = stack.popLast() {
                    let px = p % 96, py = p / 96
                    box.l = min(box.l, px); box.r = max(box.r, px + 1)
                    box.t = min(box.t, py); box.b = max(box.b, py + 1); box.area += 1
                    for q in [p - 1, p + 1, p - 96, p + 96] {
                        let qx = q % 96, qy = q / 96
                        if qx < left || qx >= right || qy < first || qy >= last || seen[q] || !eligible(q) { continue }
                        seen[q] = true; stack.append(q)
                    }
                }
                let w = box.r - box.l, h = box.b - box.t
                if w >= 3 && w <= 18 && h >= 4 && h <= 22 && box.area >= 10 && box.area <= 220 && w <= h * 2 && h <= w * 3 && boxes.count < 96 { boxes.append(box) }
            }}
            for a in boxes { for b in boxes {
                let ax = Double(a.l + a.r) / 2, bx = Double(b.l + b.r) / 2
                let ay = Double(a.t + a.b) / 2, by = Double(b.t + b.b) / 2
                if bx - ax < 10 || bx - ax > 38 || abs(ay - by) > 5 || Double(a.area) > Double(b.area) * 2.2 || Double(b.area) > Double(a.area) * 2.2 || abs((ax + bx) / 2 - center) > width * 0.2 { continue }
                let score = Double(a.area + b.area) - 8 * abs(ay - by) - 2 * abs((ax + bx) / 2 - center) - abs((ay + by) / 2 - (Double(top) + height * 0.36))
                if score <= best { continue }; best = score
                result = [a, b].map { box in
                    let x = Double(box.l + box.r) / 2.0
                    let y = Double(box.t + box.b) / 2.0
                    let rx = min(10.0, Double(box.r - box.l) / 2.0 + 1.5)
                    let ry = min(12.0, Double(box.b - box.t) / 2.0 + 1.5)
                    return DizzyEyeAnchor(x: x, y: y, rx: rx, ry: ry)
                }
            }}
        }
        return result
    }
}

struct DizzySpiralEyes: View {
    let eyes: [DizzyEyeAnchor]
    let time: Double
    // Unit spiral is cached; only two rotations are calculated per frame.
    private static let curve: [CGPoint] = (0...48).map { j in
        let k = Double(j) / 48, angle = k * 10.053096, radius = 0.04 + 0.69 * k
        return CGPoint(x: radius * cos(angle), y: radius * sin(angle))
    }
    var body: some View {
        Canvas { context, size in
            let side = min(size.width, size.height)
            context.translateBy(x: (size.width - side) / 2, y: (size.height - side) / 2)
            context.scaleBy(x: side / 96, y: side / 96)
            for (index, e) in eyes.enumerated() {
                let outer = CGRect(x: e.x - e.rx, y: e.y - e.ry, width: e.rx * 2, height: e.ry * 2)
                let navy = Color(red: 16/255, green: 24/255, blue: 58/255)
                context.fill(Path(ellipseIn: outer), with: .color(navy))
                context.fill(Path(ellipseIn: outer.insetBy(dx: e.rx * 0.12, dy: e.ry * 0.12)), with: .color(Color(red: 1, green: 250/255, blue: 230/255)))
                let angle = time * 4.4 * (index == 0 ? 1.0 : -1.0), c = cos(angle), s = sin(angle)
                let path = Path { path in
                    for (j, p) in Self.curve.enumerated() {
                        let point = CGPoint(x: e.x + (p.x * c - p.y * s) * e.rx, y: e.y + (p.x * s + p.y * c) * e.ry)
                        if j == 0 { path.move(to: point) } else { path.addLine(to: point) }
                    }
                }
                context.stroke(path, with: .color(navy), style: StrokeStyle(lineWidth: 1.1, lineCap: .round, lineJoin: .round))
            }
        }.allowsHitTesting(false).accessibilityHidden(true)
    }
}
