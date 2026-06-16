import Foundation
import FoundationModels

enum ToolError: Error, CustomStringConvertible {
    case missingArgument(String)
    case invalidSubtitlePath(String)
    case invalidOutput(String)
    case unsupportedRuntime
    case modelUnavailable(String)
    case invalidModelResponse(String)

    var description: String {
        switch self {
        case .missingArgument(let message):
            return message
        case .invalidSubtitlePath(let path):
            return "Subtitle file not found: \(path)"
        case .invalidOutput(let path):
            return "Unable to write analysis output: \(path)"
        case .unsupportedRuntime:
            return "Apple Foundation Models require macOS 26.0 or newer."
        case .modelUnavailable(let reason):
            return "Apple Foundation Models are unavailable: \(reason)"
        case .invalidModelResponse(let message):
            return "Apple Foundation Models returned invalid JSON: \(message)"
        }
    }
}

struct SRTCue {
    let start: String
    let end: String
    let startSeconds: Double
    let endSeconds: Double
    let text: String

    var block: String {
        "\(start) --> \(end)\n\(text)"
    }
}

struct TopicSection {
    let topic: String
    let start: String
    let end: String
    let startSeconds: Double
    let endSeconds: Double
}

func debugLog(_ message: String) {
    let timestamp = ISO8601DateFormatter().string(from: Date())
    fputs("[apple-foundation-key-moments \(timestamp)] \(message)\n", stderr)
}

@main
struct AppleFoundationKeyMomentsTool {
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
        guard let subtitlePath = args["srt"] else {
            throw ToolError.missingArgument("Missing required argument: --srt")
        }
        guard let outputPath = args["output"] else {
            throw ToolError.missingArgument("Missing required argument: --output")
        }
        let maxTokens = Int(args["max-tokens"] ?? "") ?? 16384

        guard FileManager.default.fileExists(atPath: subtitlePath) else {
            throw ToolError.invalidSubtitlePath(subtitlePath)
        }

        let subtitleURL = URL(fileURLWithPath: subtitlePath)
        let outputURL = URL(fileURLWithPath: outputPath)
        let subtitleContent = try String(contentsOf: subtitleURL, encoding: .utf8)
        debugLog("started srt=\(subtitlePath) bytes=\(subtitleContent.utf8.count) output=\(outputPath)")

        if #available(macOS 26.0, *) {
            let responseText = try await analyze(subtitleContent: subtitleContent, maxTokens: maxTokens)
            let jsonText = try extractJSONArray(from: responseText)
            guard let data = jsonText.data(using: .utf8) else {
                throw ToolError.invalidModelResponse("Response was not UTF-8 encodable.")
            }
            let json = try JSONSerialization.jsonObject(with: data)
            guard JSONSerialization.isValidJSONObject(json), json is [Any] else {
                throw ToolError.invalidModelResponse("Expected a top-level JSON array.")
            }
            let prettyData = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
            try FileManager.default.createDirectory(
                at: outputURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try prettyData.write(to: outputURL)
            debugLog("wrote analysis json")
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
            parsed[String(argument.dropFirst(2))] = iterator.next()
        }
        return parsed
    }

    @available(macOS 26.0, *)
    static func analyze(subtitleContent: String, maxTokens: Int) async throws -> String {
        let model = SystemLanguageModel.default
        switch model.availability {
        case .available:
            debugLog("SystemLanguageModel.default available contextSize=\(model.contextSize)")
        case .unavailable(let reason):
            throw ToolError.modelUnavailable(String(describing: reason))
        }

        let instructions = analysisInstructions()
        let prompt = analysisPrompt(subtitleContent: subtitleContent)
        let inputTokens = try await localInputTokenCount(
            model: model,
            instructions: instructions,
            prompt: prompt
        )
        let localContextSize = model.contextSize
        debugLog("local inputTokens=\(inputTokens) contextSize=\(localContextSize)")

        if inputTokens < localContextSize {
            return try await analyzeWithLocalModel(
                model: model,
                instructions: instructions,
                prompt: prompt,
                maxTokens: responseTokenBudget(maxTokens: maxTokens, inputTokens: inputTokens, contextSize: localContextSize)
            )
        }

        debugLog("input exceeds local context; using outline-and-section analysis")
        return try await analyzeByTopicSections(subtitleContent: subtitleContent)
    }

    @available(macOS 26.0, *)
    static func analyzeWithLocalModel(
        model: SystemLanguageModel,
        instructions: String,
        prompt: String,
        maxTokens: Int
    ) async throws -> String {
        debugLog("using SystemLanguageModel.default maximumResponseTokens=\(maxTokens)")
        let session = LanguageModelSession(model: model, instructions: instructions)
        let options = GenerationOptions(
            samplingMode: .greedy,
            temperature: nil,
            maximumResponseTokens: maxTokens
        )
        let response = try await session.respond(to: prompt, options: options)
        return response.content
    }

    @available(macOS 27.0, *)
    static func analyzeWithPrivateCloudCompute(
        instructions: String,
        prompt: String,
        inputTokens: Int,
        maxTokens: Int
    ) async throws -> String {
        let model = PrivateCloudComputeLanguageModel()
        switch model.availability {
        case .available:
            break
        case .unavailable(let reason):
            throw ToolError.modelUnavailable("Private Cloud Compute unavailable: \(reason)")
        }

        let contextSize = try await model.contextSize
        debugLog("PrivateCloudComputeLanguageModel available contextSize=\(contextSize) inputTokens=\(inputTokens)")
        let session = LanguageModelSession(model: model, instructions: instructions)
        let firstBudget = pccResponseTokenBudget(
            maxTokens: maxTokens,
            inputTokens: inputTokens,
            contextSize: contextSize
        )
        do {
            debugLog("using PrivateCloudComputeLanguageModel maximumResponseTokens=\(firstBudget)")
            return try await respond(
                session: session,
                prompt: prompt,
                maxTokens: firstBudget
            )
        } catch {
            let retryBudget = max(1024, firstBudget / 2)
            guard retryBudget < firstBudget else {
                throw error
            }
            debugLog("PrivateCloudComputeLanguageModel failed with \(error); retrying maximumResponseTokens=\(retryBudget)")
            return try await respond(
                session: session,
                prompt: prompt,
                maxTokens: retryBudget
            )
        }
    }

    @available(macOS 26.0, *)
    static func respondWithBestModel(
        instructions: String,
        prompt: String,
        maxTokens: Int
    ) async throws -> String {
        let localModel = SystemLanguageModel.default
        let inputTokens = try await localInputTokenCount(
            model: localModel,
            instructions: instructions,
            prompt: prompt
        )
        let localContextSize = localModel.contextSize
        debugLog("section inputTokens=\(inputTokens) localContextSize=\(localContextSize)")
        if inputTokens < localContextSize {
            return try await analyzeWithLocalModel(
                model: localModel,
                instructions: instructions,
                prompt: prompt,
                maxTokens: responseTokenBudget(maxTokens: maxTokens, inputTokens: inputTokens, contextSize: localContextSize)
            )
        }
        if #available(macOS 27.0, *) {
            return try await analyzeWithPrivateCloudCompute(
                instructions: instructions,
                prompt: prompt,
                inputTokens: inputTokens,
                maxTokens: maxTokens
            )
        }
        throw ToolError.modelUnavailable(
            "section input token count \(inputTokens) exceeds local context size \(localContextSize), and Private Cloud Compute requires macOS 27.0 or newer."
        )
    }

    @available(macOS 26.0, *)
    static func analyzeByTopicSections(subtitleContent: String) async throws -> String {
        let cues = parseSRTCues(subtitleContent)
        guard !cues.isEmpty else {
            throw ToolError.invalidModelResponse("No SRT cues were found.")
        }

        let sections = try await identifyTopicSections(subtitleContent: subtitleContent, cues: cues)
        debugLog("topic outline sections=\(sections.count)")

        var topicObjects: [Any] = []
        for (index, section) in sections.enumerated() {
            let sectionContent = contentForSection(section, cues: cues)
            guard !sectionContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                debugLog("skipping empty section index=\(index + 1) topic=\(section.topic)")
                continue
            }

            debugLog("analyzing section \(index + 1)/\(sections.count) start=\(section.start) end=\(section.end) topic=\(section.topic)")
            let responseText = try await respondWithBestModel(
                instructions: analysisInstructions(),
                prompt: singleTopicPrompt(section: section, subtitleContent: sectionContent),
                maxTokens: 1536
            )
            let objectText = try extractJSONObject(from: responseText)
            guard let data = objectText.data(using: .utf8) else {
                throw ToolError.invalidModelResponse("Section response was not UTF-8 encodable.")
            }
            let json = try JSONSerialization.jsonObject(with: data)
            guard let object = json as? [String: Any], JSONSerialization.isValidJSONObject(object) else {
                throw ToolError.invalidModelResponse("Expected section response to be a JSON object.")
            }
            topicObjects.append(object)
        }

        guard !topicObjects.isEmpty else {
            throw ToolError.invalidModelResponse("No topic summaries were generated.")
        }
        let data = try JSONSerialization.data(withJSONObject: topicObjects, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
        guard let text = String(data: data, encoding: .utf8) else {
            throw ToolError.invalidModelResponse("Combined topic response was not UTF-8 encodable.")
        }
        return text
    }

    @available(macOS 26.0, *)
    static func identifyTopicSections(subtitleContent: String, cues: [SRTCue]) async throws -> [TopicSection] {
        do {
            let responseText = try await respondWithBestModel(
                instructions: outlineInstructions(),
                prompt: outlinePrompt(subtitleContent: subtitleContent),
                maxTokens: 1024
            )
            let jsonText = try extractJSONArray(from: responseText)
            let sections = try parseTopicSections(jsonText)
            if !sections.isEmpty {
                return sections
            }
        } catch {
            debugLog("topic outline failed with \(error); falling back to fixed transcript windows")
        }

        return fallbackSections(cues: cues)
    }

    @available(macOS 26.0, *)
    static func respond(
        session: LanguageModelSession,
        prompt: String,
        maxTokens: Int
    ) async throws -> String {
        let options = GenerationOptions(
            samplingMode: .greedy,
            temperature: nil,
            maximumResponseTokens: maxTokens
        )
        let response = try await session.respond(to: prompt, options: options)
        return response.content
    }

    @available(macOS 26.0, *)
    static func localInputTokenCount(
        model: SystemLanguageModel,
        instructions: String,
        prompt: String
    ) async throws -> Int {
        if #available(macOS 26.4, *) {
            let instructionTokens = try await model.tokenCount(for: Instructions(instructions))
            let promptTokens = try await model.tokenCount(for: prompt)
            return instructionTokens + promptTokens
        }

        return max(1, (instructions.count + prompt.count) / 4)
    }

    static func responseTokenBudget(maxTokens: Int, inputTokens: Int, contextSize: Int) -> Int {
        let remaining = contextSize - inputTokens - 256
        guard remaining > 0 else {
            return maxTokens
        }
        return min(maxTokens, max(512, remaining))
    }

    static func pccResponseTokenBudget(maxTokens: Int, inputTokens: Int, contextSize: Int) -> Int {
        let remaining = contextSize - inputTokens - 4096
        guard remaining > 0 else {
            return min(maxTokens, 2048)
        }
        return min(maxTokens, 4096, max(1024, remaining))
    }

    static func analysisInstructions() -> String {
        """
        You are a meeting analyzer that identifies key moments and takeaways.
        Return only a valid JSON array. Do not include Markdown, code fences, commentary, or extra text.
        """
    }

    static func analysisPrompt(subtitleContent: String) -> String {
        """
        Analyze this meeting transcript and break it down into major topics.
        For each topic, identify key moments and extract actionable takeaways.

        Required JSON shape:
        [
          {
            "topic": "Brief topic description",
            "timestamp": "HH:MM:SS,mmm",
            "key_moments": [
              {
                "description": "Description of an important moment",
                "timestamp": "HH:MM:SS,mmm"
              }
            ],
            "takeaways": [
              "Actionable takeaway or key decision"
            ]
          }
        ]

        Rules:
        - Each topic must be a distinct point or agenda item.
        - Timestamps must use exact SRT format from the transcript: HH:MM:SS,mmm.
        - Key moments should capture significant points, decisions, or transitions.
        - Takeaways should be actionable items or important conclusions.
        - Keep descriptions concise but informative.
        - Respond only with the JSON array.

        Transcript:
        \(subtitleContent)
        """
    }

    static func outlineInstructions() -> String {
        """
        You identify high-level topic boundaries in meeting transcripts.
        Return only a valid JSON array. Do not include Markdown, code fences, commentary, or extra text.
        """
    }

    static func outlinePrompt(subtitleContent: String) -> String {
        """
        Split this SRT transcript into 4 to 12 major topic sections.

        Return only this JSON array shape:
        [
          {
            "topic": "Brief topic description",
            "start_timestamp": "HH:MM:SS,mmm",
            "end_timestamp": "HH:MM:SS,mmm"
          }
        ]

        Rules:
        - Cover the whole transcript in chronological order.
        - Use exact timestamps that appear in the SRT timing lines.
        - Keep topic descriptions concise.

        Transcript:
        \(subtitleContent)
        """
    }

    static func singleTopicPrompt(section: TopicSection, subtitleContent: String) -> String {
        """
        Analyze only this one topic section from a meeting transcript.

        Topic: \(section.topic)
        Topic range: \(section.start) to \(section.end)

        Return only one JSON object with this shape:
        {
          "topic": "Brief topic description",
          "timestamp": "HH:MM:SS,mmm",
          "key_moments": [
            {
              "description": "Description of an important moment",
              "timestamp": "HH:MM:SS,mmm"
            }
          ],
          "takeaways": [
            "Actionable takeaway or key decision"
          ]
        }

        Rules:
        - The top-level timestamp must be the topic start timestamp.
        - Timestamps must use exact SRT format from this section.
        - Include 1 to 5 key moments.
        - Include 1 to 5 concise takeaways.
        - Respond only with the JSON object.

        Section transcript:
        \(subtitleContent)
        """
    }

    static func parseSRTCues(_ content: String) -> [SRTCue] {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        return normalized.components(separatedBy: "\n\n").compactMap { rawBlock in
            let lines = rawBlock
                .split(separator: "\n", omittingEmptySubsequences: false)
                .map(String.init)
            guard lines.count >= 2 else {
                return nil
            }

            let timingLineIndex = lines.firstIndex { $0.contains(" --> ") }
            guard let timingLineIndex else {
                return nil
            }
            let timingParts = lines[timingLineIndex].components(separatedBy: " --> ")
            guard timingParts.count == 2,
                  let startSeconds = parseTimestamp(timingParts[0]),
                  let endSeconds = parseTimestamp(timingParts[1]) else {
                return nil
            }

            let text = lines.dropFirst(timingLineIndex + 1)
                .joined(separator: "\n")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                return nil
            }

            return SRTCue(
                start: timingParts[0],
                end: timingParts[1],
                startSeconds: startSeconds,
                endSeconds: endSeconds,
                text: text
            )
        }
    }

    static func parseTopicSections(_ jsonText: String) throws -> [TopicSection] {
        guard let data = jsonText.data(using: .utf8) else {
            throw ToolError.invalidModelResponse("Topic outline was not UTF-8 encodable.")
        }
        let json = try JSONSerialization.jsonObject(with: data)
        guard let array = json as? [[String: Any]] else {
            throw ToolError.invalidModelResponse("Expected topic outline to be a JSON array.")
        }

        return array.compactMap { item in
            guard let topic = item["topic"] as? String,
                  let start = item["start_timestamp"] as? String,
                  let end = item["end_timestamp"] as? String,
                  let startSeconds = parseTimestamp(start),
                  let endSeconds = parseTimestamp(end),
                  endSeconds >= startSeconds else {
                return nil
            }
            return TopicSection(
                topic: topic,
                start: start,
                end: end,
                startSeconds: startSeconds,
                endSeconds: endSeconds
            )
        }
    }

    static func fallbackSections(cues: [SRTCue]) -> [TopicSection] {
        let targetCueCount = 40
        var sections: [TopicSection] = []
        var index = 0
        while index < cues.count {
            let endIndex = min(cues.count - 1, index + targetCueCount - 1)
            let first = cues[index]
            let last = cues[endIndex]
            sections.append(
                TopicSection(
                    topic: "Transcript section \(sections.count + 1)",
                    start: first.start,
                    end: last.end,
                    startSeconds: first.startSeconds,
                    endSeconds: last.endSeconds
                )
            )
            index = endIndex + 1
        }
        return sections
    }

    static func contentForSection(_ section: TopicSection, cues: [SRTCue]) -> String {
        cues
            .filter { cue in
                cue.endSeconds >= section.startSeconds && cue.startSeconds <= section.endSeconds
            }
            .map(\.block)
            .joined(separator: "\n\n")
    }

    static func parseTimestamp(_ timestamp: String) -> Double? {
        let parts = timestamp.components(separatedBy: ",")
        guard parts.count == 2, let milliseconds = Double(parts[1]) else {
            return nil
        }
        let timeParts = parts[0].components(separatedBy: ":")
        guard timeParts.count == 3,
              let hours = Double(timeParts[0]),
              let minutes = Double(timeParts[1]),
              let seconds = Double(timeParts[2]) else {
            return nil
        }
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    }

    static func extractJSONArray(from text: String) throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.hasPrefix("[") {
            return trimmed
        }

        guard let start = trimmed.firstIndex(of: "[") else {
            throw ToolError.invalidModelResponse("No JSON array was found.")
        }

        var depth = 0
        var inString = false
        var escaped = false
        var current = start
        while current < trimmed.endIndex {
            let character = trimmed[current]
            if inString {
                if escaped {
                    escaped = false
                } else if character == "\\" {
                    escaped = true
                } else if character == "\"" {
                    inString = false
                }
            } else if character == "\"" {
                inString = true
            } else if character == "[" {
                depth += 1
            } else if character == "]" {
                depth -= 1
                if depth == 0 {
                    return String(trimmed[start...current])
                }
            }
            current = trimmed.index(after: current)
        }

        throw ToolError.invalidModelResponse("JSON array was not closed.")
    }

    static func extractJSONObject(from text: String) throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.hasPrefix("{") {
            return trimmed
        }

        guard let start = trimmed.firstIndex(of: "{") else {
            throw ToolError.invalidModelResponse("No JSON object was found.")
        }

        var depth = 0
        var inString = false
        var escaped = false
        var current = start
        while current < trimmed.endIndex {
            let character = trimmed[current]
            if inString {
                if escaped {
                    escaped = false
                } else if character == "\\" {
                    escaped = true
                } else if character == "\"" {
                    inString = false
                }
            } else if character == "\"" {
                inString = true
            } else if character == "{" {
                depth += 1
            } else if character == "}" {
                depth -= 1
                if depth == 0 {
                    return String(trimmed[start...current])
                }
            }
            current = trimmed.index(after: current)
        }

        throw ToolError.invalidModelResponse("JSON object was not closed.")
    }
}
