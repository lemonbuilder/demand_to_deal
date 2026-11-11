// macOS Vision OCR: 이미지 경로들을 받아 페이지별 텍스트 출력 (구분자 \f)
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("[[OCR_LOAD_FAIL]]"); print("\u{0C}"); continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ko-KR", "en-US"]
    req.usesLanguageCorrection = true
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try h.perform([req]) } catch { print("[[OCR_ERROR]]"); print("\u{0C}"); continue }
    let obs = (req.results ?? []).sorted { a, b in
        let ya = a.boundingBox.midY, yb = b.boundingBox.midY
        if abs(ya - yb) > 0.01 { return ya > yb }
        return a.boundingBox.minX < b.boundingBox.minX
    }
    for o in obs { if let c = o.topCandidates(1).first { print(c.string) } }
    print("\u{0C}")
}
