// Local worksheet OCR. Images never leave this computer.
// Bounding boxes use normalized [x, y, width, height] coordinates, with a
// top-left origin, after applying the image's EXIF orientation.
import Foundation
import ImageIO
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard CommandLine.arguments.count == 2 else {
    fail("Usage: worksheet-ocr IMAGE_PATH")
}
let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fail("Apple Vision could not open the worksheet image.")
}
guard image.width <= 30000, image.height <= 30000,
      image.width * image.height <= 100_000_000 else {
    fail("The worksheet image is too large. Resize it below 100 megapixels.")
}
let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
let rawOrientation = (properties?[kCGImagePropertyOrientation] as? NSNumber)?.uint32Value ?? 1
let orientation = CGImagePropertyOrientation(rawValue: rawOrientation) ?? .up
let rotated = [5, 6, 7, 8].contains(rawOrientation)
let width = rotated ? image.height : image.width
let height = rotated ? image.width : image.height

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = false
request.minimumTextHeight = 0.008
if #available(macOS 13.0, *) {
    request.automaticallyDetectsLanguage = false
}

do {
    let handler = VNImageRequestHandler(cgImage: image, orientation: orientation, options: [:])
    try handler.perform([request])
    var lines: [[String: Any]] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let box = observation.boundingBox
        lines.append([
            "text": candidate.string,
            "confidence": Double(candidate.confidence),
            "bbox": [Double(box.minX), Double(1 - box.maxY),
                     Double(box.width), Double(box.height)]
        ])
    }
    // Vision normally returns reading order; normalize it for multirow worksheets.
    lines.sort { left, right in
        let a = left["bbox"] as! [Double]
        let b = right["bbox"] as! [Double]
        if abs(a[1] - b[1]) < min(a[3], b[3]) * 0.4 { return a[0] < b[0] }
        return a[1] < b[1]
    }
    let output: [String: Any] = [
        "text": lines.compactMap { $0["text"] as? String }.joined(separator: "\n"),
        "lines": lines,
        "engine": "Apple Vision",
        "image_width": width,
        "image_height": height,
        "bbox_coordinates": "normalized-top-left-after-exif-orientation"
    ]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    fail("Apple Vision text recognition failed: \(error.localizedDescription)")
}
