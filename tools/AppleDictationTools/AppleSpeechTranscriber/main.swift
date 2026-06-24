import AVFoundation
import CoreMedia
import Foundation
import Speech

struct TranscriptChunk: Codable {
    let timestamp: [Double]
    let text: String
    let confidence: Double?
    let locale: String?
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
            return "Apple SpeechTranscriber requires macOS 26.0 or newer."
        case .invalidAudioPath(let path):
            return "Audio file not found: \(path)"
        }
    }
}

func debugLog(_ message: String) {
    let timestamp = ISO8601DateFormatter().string(from: Date())
    fputs("[apple-speech \(timestamp)] \(message)\n", stderr)
}

@main
struct AppleSpeechTranscriberTool {
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
        let comparisonLocaleIdentifier = args["compare-locale"]

        guard FileManager.default.fileExists(atPath: audioPath) else {
            throw ToolError.invalidAudioPath(audioPath)
        }
        let fileSize = (try? FileManager.default.attributesOfItem(atPath: audioPath)[.size] as? NSNumber)?.int64Value
        debugLog("audio=\(audioPath) bytes=\(fileSize.map(String.init) ?? "unknown") locale=\(localeIdentifier) compareLocale=\(comparisonLocaleIdentifier ?? "none")")
        debugLog("outputs transcript=\(transcriptPath) srt=\(srtPath)")

        if #available(macOS 26.0, *) {
            let primaryChunks = try await transcribe(
                audioURL: URL(fileURLWithPath: audioPath),
                locale: Locale(identifier: localeIdentifier)
            )
            let chunks: [TranscriptChunk]
            if let comparisonLocaleIdentifier,
               comparisonLocaleIdentifier != localeIdentifier {
                let comparisonChunks = try await transcribe(
                    audioURL: URL(fileURLWithPath: audioPath),
                    locale: Locale(identifier: comparisonLocaleIdentifier)
                )
                chunks = selectBestTimeline(primaryChunks + comparisonChunks)
                debugLog(
                    "selected comparison timeline primary=\(primaryChunks.count) comparison=\(comparisonChunks.count) output=\(chunks.count)"
                )
            } else {
                chunks = primaryChunks
            }
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
            try writeSRT(chunks: chunks, to: URL(fileURLWithPath: srtPath))
            debugLog("wrote outputs")
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
        debugLog("creating SpeechTranscriber locale=\(locale.identifier) preset=timeIndexedProgressiveTranscription")
        let supportedEquivalent = await SpeechTranscriber.supportedLocale(equivalentTo: locale)
        debugLog("SpeechTranscriber.supportedLocale=\(String(describing: supportedEquivalent))")
        let installedLocales = await SpeechTranscriber.installedLocales
        debugLog("SpeechTranscriber.installedLocales=\(installedLocales.map(\.identifier).sorted())")

        let effectiveLocale = supportedEquivalent ?? locale
        debugLog("effective locale=\(effectiveLocale.identifier)")
        let transcriber = SpeechTranscriber(
            locale: effectiveLocale,
            transcriptionOptions: [],
            reportingOptions: [.volatileResults],
            attributeOptions: [.audioTimeRange, .transcriptionConfidence]
        )
        let modules: [any SpeechModule] = [transcriber]

        let status = await AssetInventory.status(forModules: modules)
        debugLog("AssetInventory.status=\(status)")
        if status != .installed {
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
        let analyzer = SpeechAnalyzer(modules: modules)

        var resultTaskChunks: [TranscriptChunk] = []
        let resultTask = Task {
            var finalizedChunks: [TranscriptChunk] = []
            var currentChunks: [TranscriptChunk] = []
            var currentStart: Double?
            var currentEnd: Double?
            var rawResultCount = 0
            var discardedVolatileCount = 0
            for try await result in transcriber.results {
                let attributedText = result.text
                let text = String(attributedText.characters)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else {
                    continue
                }

                let start = max(0.0, CMTimeGetSeconds(result.range.start))
                let duration = max(0.0, CMTimeGetSeconds(result.range.duration))
                let end = max(start, start + duration)
                let splitChunks = splitResultText(
                    text,
                    start: start,
                    end: end,
                    confidence: averageConfidence(attributedText),
                    locale: effectiveLocale.identifier
                )
                rawResultCount += 1

                if let previousStart = currentStart, abs(start - previousStart) > 0.001 {
                    if let previousEnd = currentEnd, previousEnd <= start + 0.5 {
                        finalizedChunks.append(contentsOf: currentChunks)
                    } else {
                        discardedVolatileCount += currentChunks.count
                    }
                    currentChunks = []
                }

                currentStart = start
                currentEnd = end
                currentChunks = splitChunks
            }
            if currentStart != nil {
                finalizedChunks.append(contentsOf: currentChunks)
            }
            debugLog(
                "result stream finished raw=\(rawResultCount) finalizedChunks=\(finalizedChunks.count) discardedVolatile=\(discardedVolatileCount)"
            )
            return finalizedChunks
        }

        try await analyzer.start(inputAudioFile: audioFile, finishAfterFile: true)
        resultTaskChunks = try await resultTask.value
        let merged = mergeAdjacentDuplicates(resultTaskChunks)
        debugLog("merged adjacent duplicates input=\(resultTaskChunks.count) output=\(merged.count)")
        return merged
    }

    static func splitResultText(
        _ text: String,
        start: Double,
        end: Double,
        confidence: Double?,
        locale: String?
    ) -> [TranscriptChunk] {
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
                    text: cleaned,
                    confidence: confidence.map(roundToMillis),
                    locale: locale
                )
            ]
        }

        let totalCount = max(1, cleaned.count)
        return spans.map { span in
            let spanStart = start + duration * (Double(span.startOffset) / Double(totalCount))
            let spanEnd = start + duration * (Double(span.endOffset) / Double(totalCount))
            return TranscriptChunk(
                timestamp: [roundToMillis(spanStart), roundToMillis(max(spanStart, spanEnd))],
                text: span.text,
                confidence: confidence.map(roundToMillis),
                locale: locale
            )
        }
    }

    @available(macOS 26.0, *)
    static func averageConfidence(_ attributedText: AttributedString) -> Double? {
        var weightedSum = 0.0
        var totalCharacters = 0

        for run in attributedText.runs {
            guard let confidence = run[AttributeScopes.SpeechAttributes.ConfidenceAttribute.self] else {
                continue
            }
            let text = String(attributedText[run.range].characters)
            let count = max(1, text.count)
            weightedSum += confidence * Double(count)
            totalCharacters += count
        }

        guard totalCharacters > 0 else {
            return nil
        }
        return max(0.0, min(1.0, weightedSum / Double(totalCharacters)))
    }

    static func selectBestTimeline(_ chunks: [TranscriptChunk]) -> [TranscriptChunk] {
        let validChunks = chunks.filter { chunk in
            guard let start = chunk.timestamp.first,
                  let end = chunk.timestamp.dropFirst().first else {
                return false
            }
            return end > start && !chunk.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        let sorted = validChunks.sorted { left, right in
            let leftEnd = left.timestamp.dropFirst().first ?? 0.0
            let rightEnd = right.timestamp.dropFirst().first ?? 0.0
            if leftEnd == rightEnd {
                return chunkScore(left) > chunkScore(right)
            }
            return leftEnd < rightEnd
        }

        guard !sorted.isEmpty else {
            return []
        }

        var previousCompatible = Array(repeating: 0, count: sorted.count)
        for index in sorted.indices {
            let start = sorted[index].timestamp.first ?? 0.0
            var compatible = 0
            for candidate in stride(from: index - 1, through: 0, by: -1) {
                let candidateEnd = sorted[candidate].timestamp.dropFirst().first ?? 0.0
                if candidateEnd <= start + 0.25 {
                    compatible = candidate + 1
                    break
                }
            }
            previousCompatible[index] = compatible
        }

        var bestScores = Array(repeating: 0.0, count: sorted.count + 1)
        var selected = Array(repeating: false, count: sorted.count)
        for index in sorted.indices {
            let includeScore = chunkScore(sorted[index]) + bestScores[previousCompatible[index]]
            let excludeScore = bestScores[index]
            if includeScore > excludeScore {
                bestScores[index + 1] = includeScore
                selected[index] = true
            } else {
                bestScores[index + 1] = excludeScore
            }
        }

        var output: [TranscriptChunk] = []
        var index = sorted.count - 1
        while index >= 0 {
            let includeScore = chunkScore(sorted[index]) + bestScores[previousCompatible[index]]
            let excludeScore = bestScores[index]
            if selected[index] && includeScore >= excludeScore {
                output.append(sorted[index])
                index = previousCompatible[index] - 1
            } else {
                index -= 1
            }
        }

        return output.reversed().sorted { left, right in
            (left.timestamp.first ?? 0.0) < (right.timestamp.first ?? 0.0)
        }
    }

    static func chunkScore(_ chunk: TranscriptChunk) -> Double {
        let start = chunk.timestamp.first ?? 0.0
        let end = chunk.timestamp.dropFirst().first ?? start
        let duration = max(0.1, end - start)
        let confidence = chunk.confidence ?? 0.5
        return duration * confidence * textQualityScore(chunk.text, locale: chunk.locale)
    }

    static func textQualityScore(_ text: String, locale: String?) -> Double {
        let characters = text.filter { !$0.isWhitespace }
        guard !characters.isEmpty else {
            return 0.0
        }

        let replacementPenalty = text.contains("�") ? 0.5 : 1.0
        let repeatedPunctuationPenalty = text.contains("...") || text.contains("???") ? 0.8 : 1.0
        let cjkCount = characters.filter { character in
            character.unicodeScalars.contains { scalar in
                (0x3040...0x30FF).contains(Int(scalar.value)) ||
                    (0x3400...0x9FFF).contains(Int(scalar.value))
            }
        }.count
        let asciiLetterCount = characters.filter { character in
            character.unicodeScalars.allSatisfy { scalar in
                (65...90).contains(Int(scalar.value)) || (97...122).contains(Int(scalar.value))
            }
        }.count

        let localeIdentifier = locale ?? ""
        let languageFit: Double
        if localeIdentifier.hasPrefix("ja") {
            languageFit = cjkCount > 0 ? 1.0 : 0.65
        } else if localeIdentifier.hasPrefix("en") {
            languageFit = asciiLetterCount > 0 ? 1.0 : 0.65
        } else {
            languageFit = 1.0
        }

        let veryShortPenalty = characters.count <= 2 ? 0.55 : 1.0
        return replacementPenalty * repeatedPunctuationPenalty * languageFit * veryShortPenalty
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
