import AVFoundation
import CoreMedia
import Foundation
import Speech

struct TranscriptChunk: Codable {
    let timestamp: [Double]
    let text: String
}

struct Transcript: Codable {
    let speakers: [String]
    let chunks: [TranscriptChunk]
    let text: String
}

struct TextSpan {
    let text: String
    let startOffset: Int
    let endOffset: Int
}

enum ToolError: Error, CustomStringConvertible {
    case missingArgument(String)
    case unsupportedRuntime
    case invalidAudioPath(String)

    var description: String {
        switch self {
        case .missingArgument(let message):
            return message
        case .unsupportedRuntime:
            return "Apple DictationTranscriber requires macOS 26.0 or newer."
        case .invalidAudioPath(let path):
            return "Audio file not found: \(path)"
        }
    }
}

func debugLog(_ message: String) {
    let timestamp = ISO8601DateFormatter().string(from: Date())
    fputs("[apple-dictation \(timestamp)] \(message)\n", stderr)
}

@main
struct AppleDictationTranscriberTool {
    static func main() async {
        do {
            try await run()
        } catch {
            fputs("Error: \(error)\n", stderr)
            exit(1)
        }
    }

    static func run() async throws {
        let args = parseArguments(CommandLine.arguments.dropFirst())
        debugLog("started argv=\(CommandLine.arguments.dropFirst().joined(separator: " "))")
        guard let audioPath = args["audio"] else {
            throw ToolError.missingArgument("Missing required argument: --audio")
        }
        guard let transcriptPath = args["transcript"] else {
            throw ToolError.missingArgument("Missing required argument: --transcript")
        }
        guard let srtPath = args["srt"] else {
            throw ToolError.missingArgument("Missing required argument: --srt")
        }
        let localeIdentifier = args["locale"] ?? "en-US"

        guard FileManager.default.fileExists(atPath: audioPath) else {
            throw ToolError.invalidAudioPath(audioPath)
        }
        if let attrs = try? FileManager.default.attributesOfItem(atPath: audioPath),
           let size = attrs[.size] as? NSNumber {
            debugLog("audio path=\(audioPath) bytes=\(size)")
        } else {
            debugLog("audio path=\(audioPath) bytes=unknown")
        }
        debugLog("outputs transcript=\(transcriptPath) srt=\(srtPath) locale=\(localeIdentifier)")

        if #available(macOS 26.0, *) {
            debugLog("runtime macOS 26 API path available")
            let chunks = try await transcribe(
                audioURL: URL(fileURLWithPath: audioPath),
                locale: Locale(identifier: localeIdentifier)
            )
            debugLog("transcription returned chunks=\(chunks.count)")
            let transcript = Transcript(
                speakers: [],
                chunks: chunks,
                text: chunks.map(\.text).joined(separator: " ")
            )

            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: transcriptPath).deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: srtPath).deletingLastPathComponent(),
                withIntermediateDirectories: true
            )

            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
            try encoder.encode(transcript).write(to: URL(fileURLWithPath: transcriptPath))
            debugLog("wrote transcript json")
            try writeSRT(chunks: chunks, to: URL(fileURLWithPath: srtPath))
            debugLog("wrote srt")
        } else {
            throw ToolError.unsupportedRuntime
        }
    }

    static func parseArguments<S: Sequence>(_ arguments: S) -> [String: String] where S.Element == String {
        var parsed: [String: String] = [:]
        var iterator = arguments.makeIterator()
        while let argument = iterator.next() {
            guard argument.hasPrefix("--") else {
                continue
            }
            let key = String(argument.dropFirst(2))
            parsed[key] = iterator.next()
        }
        return parsed
    }

    @available(macOS 26.0, *)
    static func transcribe(audioURL: URL, locale: Locale) async throws -> [TranscriptChunk] {
        debugLog("creating DictationTranscriber locale=\(locale.identifier) preset=timeIndexedLongDictation")
        let supportedEquivalent = await DictationTranscriber.supportedLocale(equivalentTo: locale)
        debugLog("DictationTranscriber.supportedLocale=\(String(describing: supportedEquivalent))")
        let installedLocales = await DictationTranscriber.installedLocales
        debugLog("DictationTranscriber.installedLocales=\(installedLocales.map(\.identifier).sorted())")

        let effectiveLocale = supportedEquivalent ?? locale
        debugLog("effective locale=\(effectiveLocale.identifier)")
        let transcriber = DictationTranscriber(
            locale: effectiveLocale,
            contentHints: [.farField],
            transcriptionOptions: [.punctuation],
            reportingOptions: [],
            attributeOptions: [.audioTimeRange]
        )
        let modules: [any SpeechModule] = [transcriber]

        debugLog("checking AssetInventory status")
        let status = await AssetInventory.status(forModules: modules)
        debugLog("AssetInventory.status=\(status)")
        if status != .installed {
            debugLog("requesting asset installation")
            if let request = try await AssetInventory.assetInstallationRequest(supporting: modules) {
                debugLog("downloading/installing speech assets")
                try await request.downloadAndInstall()
                debugLog("asset installation completed")
            } else {
                debugLog("asset installation request unavailable")
            }
        }

        debugLog("opening audio file")
        let audioFile = try AVAudioFile(forReading: audioURL)
        debugLog(
            "audio format sampleRate=\(audioFile.processingFormat.sampleRate) channels=\(audioFile.processingFormat.channelCount) frames=\(audioFile.length)"
        )
        debugLog("constructing SpeechAnalyzer")
        let analyzer = SpeechAnalyzer(modules: modules)
        debugLog("SpeechAnalyzer constructed")

        var resultTaskChunks: [TranscriptChunk] = []
        debugLog("starting result stream task")
        let resultTask = Task {
            var chunks: [TranscriptChunk] = []
            for try await result in transcriber.results {
                let text = String(result.text.characters)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else {
                    continue
                }

                let start = max(0.0, CMTimeGetSeconds(result.range.start))
                let duration = max(0.0, CMTimeGetSeconds(result.range.duration))
                let end = max(start, start + duration)
                let splitChunks = splitResultText(text, start: start, end: end)
                debugLog(
                    "result chunk start=\(roundToMillis(start)) end=\(roundToMillis(end)) chars=\(text.count) split=\(splitChunks.count)"
                )
                chunks.append(contentsOf: splitChunks)
            }
            debugLog("result stream finished chunks=\(chunks.count)")
            return chunks
        }

        debugLog("starting analyzer")
        try await analyzer.start(inputAudioFile: audioFile, finishAfterFile: true)
        debugLog("analyzer completed; awaiting result task")
        resultTaskChunks = try await resultTask.value
        let merged = mergeAdjacentDuplicates(resultTaskChunks)
        debugLog("merged adjacent duplicates input=\(resultTaskChunks.count) output=\(merged.count)")
        return merged
    }

    static func splitResultText(_ text: String, start: Double, end: Double) -> [TranscriptChunk] {
        let cleaned = normalizeWhitespace(text)
        guard !cleaned.isEmpty else {
            return []
        }

        let duration = max(0.0, end - start)
        let spans = splitIntoReadableSpans(cleaned)
        guard !spans.isEmpty else {
            return [
                TranscriptChunk(
                    timestamp: [roundToMillis(start), roundToMillis(end)],
                    text: cleaned
                )
            ]
        }

        let totalCount = max(1, cleaned.count)
        return spans.map { span in
            let spanStart = start + duration * (Double(span.startOffset) / Double(totalCount))
            let spanEnd = start + duration * (Double(span.endOffset) / Double(totalCount))
            return TranscriptChunk(
                timestamp: [roundToMillis(spanStart), roundToMillis(max(spanStart, spanEnd))],
                text: span.text
            )
        }
    }

    static func splitIntoReadableSpans(_ text: String) -> [TextSpan] {
        let maxCharacters = 120
        let minSentenceCharacters = 24
        var spans: [TextSpan] = []
        var spanStart = 0
        var lastBoundary: Int?
        var currentIndex = 0

        for character in text {
            currentIndex += 1
            if isSentenceBoundary(character) {
                lastBoundary = currentIndex
            }

            if currentIndex - spanStart >= maxCharacters {
                let splitAt: Int
                if let boundary = lastBoundary, boundary - spanStart >= minSentenceCharacters {
                    splitAt = boundary
                } else if let wordBreak = lastWhitespaceOffset(in: text, from: spanStart, through: currentIndex),
                          wordBreak - spanStart >= minSentenceCharacters {
                    splitAt = wordBreak
                } else {
                    splitAt = currentIndex
                }
                appendSpan(text, startOffset: spanStart, endOffset: splitAt, to: &spans)
                spanStart = skipSpaces(text, from: splitAt)
                lastBoundary = nil
            } else if let boundary = lastBoundary, boundary - spanStart >= minSentenceCharacters {
                appendSpan(text, startOffset: spanStart, endOffset: boundary, to: &spans)
                spanStart = skipSpaces(text, from: boundary)
                lastBoundary = nil
            }
        }

        appendSpan(text, startOffset: spanStart, endOffset: text.count, to: &spans)
        return splitLongSpans(spans, maxCharacters: maxCharacters)
    }

    static func splitLongSpans(_ spans: [TextSpan], maxCharacters: Int) -> [TextSpan] {
        var output: [TextSpan] = []
        for span in spans {
            if span.text.count <= maxCharacters {
                output.append(span)
                continue
            }

            var localStart = 0
            while localStart < span.text.count {
                let remaining = span.text.count - localStart
                var localEnd = localStart + min(maxCharacters, remaining)
                if localEnd < span.text.count,
                   let wordBreak = lastWhitespaceOffset(in: span.text, from: localStart, through: localEnd),
                   wordBreak > localStart {
                    localEnd = wordBreak
                }
                appendSpan(
                    span.text,
                    startOffset: localStart,
                    endOffset: localEnd,
                    globalOffset: span.startOffset,
                    to: &output
                )
                localStart = skipSpaces(span.text, from: localEnd)
            }
        }
        return output
    }

    static func appendSpan(
        _ text: String,
        startOffset: Int,
        endOffset: Int,
        globalOffset: Int = 0,
        to spans: inout [TextSpan]
    ) {
        guard endOffset > startOffset else {
            return
        }
        let startIndex = text.index(text.startIndex, offsetBy: startOffset)
        let endIndex = text.index(text.startIndex, offsetBy: endOffset)
        let spanText = String(text[startIndex..<endIndex])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !spanText.isEmpty else {
            return
        }
        spans.append(
            TextSpan(
                text: spanText,
                startOffset: globalOffset + startOffset,
                endOffset: globalOffset + endOffset
            )
        )
    }

    static func normalizeWhitespace(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    static func isSentenceBoundary(_ character: Character) -> Bool {
        character == "." || character == "?" || character == "!" || character == "\n"
    }

    static func skipSpaces(_ text: String, from offset: Int) -> Int {
        var next = offset
        while next < text.count {
            let index = text.index(text.startIndex, offsetBy: next)
            if !text[index].isWhitespace {
                break
            }
            next += 1
        }
        return next
    }

    static func lastWhitespaceOffset(in text: String, from start: Int, through end: Int) -> Int? {
        guard end > start else {
            return nil
        }

        var offset = start
        var lastWhitespace: Int?
        for character in text {
            if offset > end {
                break
            }
            if offset >= start && character.isWhitespace {
                lastWhitespace = offset
            }
            offset += 1
        }
        return lastWhitespace
    }

    static func mergeAdjacentDuplicates(_ chunks: [TranscriptChunk]) -> [TranscriptChunk] {
        var merged: [TranscriptChunk] = []
        for chunk in chunks {
            if merged.last?.text == chunk.text {
                continue
            }
            merged.append(chunk)
        }
        return merged
    }

    static func writeSRT(chunks: [TranscriptChunk], to url: URL) throws {
        var output = ""
        for (index, chunk) in chunks.enumerated() {
            let start = chunk.timestamp.first ?? 0.0
            let end = chunk.timestamp.dropFirst().first ?? start
            output += "\(index + 1)\n"
            output += "\(formatTimestamp(start)) --> \(formatTimestamp(end))\n"
            output += "\(chunk.text)\n\n"
        }
        try output.write(to: url, atomically: true, encoding: .utf8)
    }

    static func roundToMillis(_ value: Double) -> Double {
        (value * 1000.0).rounded() / 1000.0
    }

    static func formatTimestamp(_ seconds: Double) -> String {
        let safeSeconds = max(0.0, seconds)
        let millisecondsTotal = Int((safeSeconds * 1000.0).rounded())
        let hours = millisecondsTotal / 3_600_000
        let minutes = (millisecondsTotal % 3_600_000) / 60_000
        let secs = (millisecondsTotal % 60_000) / 1000
        let millis = millisecondsTotal % 1000
        return String(format: "%02d:%02d:%02d,%03d", hours, minutes, secs, millis)
    }
}
