import AVFoundation
// Original nonverbal cues: small, soft envelopes, no speech files or third-party recordings.
// .ambient respects the Ring/Silent switch and other audio. Never loops while thinking.
@MainActor final class PipSound {
    static let shared=PipSound()
    private var player:AVAudioPlayer?
    private var last=Date.distantPast
    func stop(){player?.stop()}
    func play(rig:Int,cue:String,preview:Bool=false){
        guard cue != "none",preview || Date().timeIntervalSince(last)>4 else{return}
        last=Date();stop()
        let rate=22050, length=0.42, count=Int(Double(rate)*length)
        let base=[520.0,680.0,350.0][rig>=3 ? 0:max(0,rig)]
        let rise=cue=="joy" ? 1.5:cue=="curious" ? 1.25:cue=="hello" ? 1.15:0.85
        var samples=[Int16]();samples.reserveCapacity(count)
        var phase=0.0
        for i in 0..<count {
            let t=Double(i)/Double(rate),u=t/length
            let envelope=pow(sin(.pi*u),2)*0.13
            let frequency=base*(1+(rise-1)*u)+sin(t*24)*12
            phase += 2 * .pi * frequency/Double(rate)
            let harmonic=rig==2 ? sin(phase*2)*0.16:sin(phase*3)*0.04
            samples.append(Int16(max(-32767,min(32767,(sin(phase)+harmonic)*envelope*32767))))
        }
        var wav=Data()
        func ascii(_ s:String){wav.append(contentsOf:s.utf8)}
        func u32(_ n:UInt32){var n=n.littleEndian;withUnsafeBytes(of:&n){wav.append(contentsOf:$0)}}
        func u16(_ n:UInt16){var n=n.littleEndian;withUnsafeBytes(of:&n){wav.append(contentsOf:$0)}}
        ascii("RIFF");u32(UInt32(36+count*2));ascii("WAVEfmt ");u32(16);u16(1);u16(1);u32(UInt32(rate));u32(UInt32(rate*2));u16(2);u16(16);ascii("data");u32(UInt32(count*2))
        for sample in samples {u16(UInt16(bitPattern:sample))}
        do {try AVAudioSession.sharedInstance().setCategory(.ambient,mode:.default);player=try AVAudioPlayer(data:wav);player?.play()}catch{player=nil}
    }
}
