import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var isProcessing = false
    @State private var dragOver = false
    @State private var lastProcessedFile: String?
    @State private var errorMessage: String?
    
    var body: some View {
        VStack {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(dragOver ? Color.blue.opacity(0.3) : Color.gray.opacity(0.2))
                    .frame(width: 300, height: 200)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(dragOver ? Color.blue : Color.gray, lineWidth: 2)
                    )
                
                VStack {
                    Image(systemName: isProcessing ? "arrow.clockwise.circle" : "arrow.down.circle")
                        .font(.system(size: 40))
                        .rotationEffect(.degrees(isProcessing ? 360 : 0))
                        .animation(isProcessing ? Animation.linear(duration: 1).repeatForever(autoreverses: false) : .default, value: isProcessing)
                    
                    Text(isProcessing ? "Processing..." : "Drop Video Here")
                        .font(.headline)
                        .padding(.top, 8)
                }
            }
            .onDrop(of: [UTType.movie], isTargeted: $dragOver) { providers in
                guard let provider = providers.first else { return false }
                
                provider.loadItem(forTypeIdentifier: UTType.movie.identifier, options: nil) { item, error in
                    if let error = error {
                        DispatchQueue.main.async {
                            self.errorMessage = error.localizedDescription
                        }
                        return
                    }
                    
                    guard let url = item as? URL else { return }
                    
                    DispatchQueue.main.async {
                        self.processVideo(at: url)
                    }
                }
                return true
            }
            
            if let lastFile = lastProcessedFile {
                Text("Last processed: \(lastFile)")
                    .font(.caption)
                    .foregroundColor(.gray)
                    .padding(.top, 8)
            }
            
            if let error = errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .padding(.top, 8)
            }
        }
        .padding()
    }
    
    private func processVideo(at url: URL) {
        isProcessing = true
        errorMessage = nil
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "\(FileManager.default.currentDirectoryPath)/src/main.py", url.path]
        
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        
        do {
            try process.run()
            process.waitUntilExit()
            
            DispatchQueue.main.async {
                self.isProcessing = false
                if process.terminationStatus == 0 {
                    self.lastProcessedFile = url.lastPathComponent
                } else {
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    self.errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
                }
            }
        } catch {
            DispatchQueue.main.async {
                self.isProcessing = false
                self.errorMessage = error.localizedDescription
            }
        }
    }
}

#Preview {
    ContentView()
}
