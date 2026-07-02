import AppKit
import Foundation
import Vision

if CommandLine.arguments.count < 2 {
    fputs("Usage: swift ocr_image.swift /path/to/image\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let nsImage = NSImage(contentsOf: imageURL),
      let cgImage = nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("Could not load image: \(imageURL.path)\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "en-US"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])

let observations = request.results ?? []
let lines = observations.compactMap { observation -> (text: String, y: CGFloat, x: CGFloat)? in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let text = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty { return nil }
    return (text, observation.boundingBox.midY, observation.boundingBox.minX)
}

let sortedLines = lines.sorted { left, right in
    if abs(left.y - right.y) > 0.01 {
        return left.y > right.y
    }
    return left.x < right.x
}

for line in sortedLines {
    print(line.text)
}

