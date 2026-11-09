import Foundation
import Vision
import AppKit

// macOS Vision OCR with bounding boxes: `ocr_box <image> [<image> ...]`
// Output: "@@@ <path>" then "<text>\t<cx>\t<cy>" with normalized coords (origin = top-left).
// Coordinates matter: the whole point of this tool over a plain OCR pass is that the chat bubble
// on the right (cx > 0.62) can be told apart from the assistant's reply on the left.
// Language: OCR_LANG env var, comma-separated (default "en-US"; e.g. "zh-Hans,en-US").
let args = Array(CommandLine.arguments.dropFirst())
guard !args.isEmpty else { exit(2) }
let langs = (ProcessInfo.processInfo.environment["OCR_LANG"] ?? "en-US")
    .split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }

for path in args {
    let url = URL(fileURLWithPath: path)
    guard let img = NSImage(contentsOf: url),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("@@@ \(path)")
        print("(unreadable)")
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = langs
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    print("@@@ \(path)")
    do {
        try handler.perform([request])
        for obs in request.results ?? [] {
            if let c = obs.topCandidates(1).first {
                let bb = obs.boundingBox
                let cx = bb.origin.x + bb.width / 2.0
                let cy = 1.0 - (bb.origin.y + bb.height / 2.0)
                print(String(format: "%@\t%.4f\t%.4f", c.string, cx, cy))
            }
        }
    } catch {
        print("(ocr failed)")
    }
}
