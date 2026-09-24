#if os(macOS)
import SwiftUI
import AllyDesktopCore

private enum SidebarSelection: Hashable {
    case conversation(String)
    case memory
    case knowledge
    case tasks
    case system
}

@main
struct AllyDesktopApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .frame(minWidth: 920, minHeight: 620)
                .task {
                    await model.refresh()
                }
        }
    }
}

private struct RootView: View {
    @ObservedObject var model: AppModel
    @State private var selection: SidebarSelection? = .system

    var body: some View {
        NavigationSplitView {
            List(selection: $selection) {
                Section("Conversations") {
                    ForEach(model.snapshot?.conversations.items ?? []) { conversation in
                        Text(conversation.title ?? "Conversation")
                            .tag(SidebarSelection.conversation(conversation.id))
                    }
                    Button {
                        Task {
                            await model.createConversation()
                            if let id = model.selectedConversationID {
                                selection = .conversation(id)
                            }
                        }
                    } label: {
                        Label("New Conversation", systemImage: "square.and.pencil")
                    }
                    .buttonStyle(.plain)
                }

                Section("Ally") {
                    Label("Memory", systemImage: "brain.head.profile")
                        .tag(SidebarSelection.memory)
                    Label("Knowledge", systemImage: "books.vertical")
                        .tag(SidebarSelection.knowledge)
                    Label("Tasks", systemImage: "checklist")
                        .tag(SidebarSelection.tasks)
                    Label("System", systemImage: "gauge.with.dots.needle.67percent")
                        .tag(SidebarSelection.system)
                }
            }
            .navigationTitle("Ally")
        } detail: {
            Group {
                switch selection {
                case .conversation(let id):
                    ConversationScreen(model: model, conversationID: id)
                case .memory:
                    MemoryScreen(model: model)
                case .knowledge:
                    KnowledgeScreen(model: model)
                case .tasks:
                    TasksScreen(model: model)
                case .system, .none:
                    SystemScreen(model: model)
                }
            }
            .toolbar {
                ToolbarItem {
                    Button {
                        Task { await model.refresh() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(model.isBusy)
                }
            }
        }
        .overlay(alignment: .bottom) {
            if let error = model.errorMessage {
                Text(error)
                    .font(.callout)
                    .padding(10)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
                    .padding()
            }
        }
    }
}

private struct ConversationScreen: View {
    @ObservedObject var model: AppModel
    let conversationID: String

    var body: some View {
        VStack(spacing: 0) {
            if model.snapshot?.runtime.state != "ready" {
                Text("Private inference is unavailable until a validated local runtime profile is selected.")
                    .font(.callout)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(.quaternary)
            }

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    ForEach(model.conversation?.messages ?? []) { message in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(message.role == "user" ? "You" : "Ally")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(message.content)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding()
            }

            Divider()
            HStack(alignment: .bottom) {
                TextField("Message Ally", text: $model.composer, axis: .vertical)
                    .lineLimit(1...6)
                    .textFieldStyle(.roundedBorder)
                Button("Send") {
                    Task { await model.sendMessage() }
                }
                .keyboardShortcut(.return, modifiers: [.command])
                .disabled(model.isBusy || model.composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
        .navigationTitle(model.conversation?.conversation.title ?? "Conversation")
        .task(id: conversationID) {
            await model.selectConversation(conversationID)
        }
    }
}

private struct MemoryScreen: View {
    @ObservedObject var model: AppModel

    var body: some View {
        List(model.memories) { memory in
            VStack(alignment: .leading, spacing: 5) {
                Text(memory.content)
                HStack {
                    Text(memory.kind)
                    Text(memory.privacy)
                    Text("importance \(memory.importance, format: .number.precision(.fractionLength(2)))")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
        .navigationTitle("Memory")
    }
}

private struct KnowledgeScreen: View {
    @ObservedObject var model: AppModel

    var body: some View {
        List(model.knowledge) { source in
            VStack(alignment: .leading, spacing: 5) {
                Text(source.title)
                Text(source.uri)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .padding(.vertical, 4)
        }
        .navigationTitle("Knowledge")
    }
}

private struct TasksScreen: View {
    @ObservedObject var model: AppModel

    var body: some View {
        NavigationStack {
            List(model.snapshot?.tasks.items ?? []) { task in
                NavigationLink(value: task.id) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(task.goal)
                        HStack(spacing: 8) {
                            Text(task.status.replacingOccurrences(of: "_", with: " ").capitalized)
                            if task.status == "waiting_approval" {
                                Label("Approval required", systemImage: "hand.raised.fill")
                            }
                        }
                        .font(.caption)
                        .foregroundStyle(task.status == "waiting_approval" ? .primary : .secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
            .navigationTitle("Tasks")
            .navigationDestination(for: String.self) { taskID in
                TaskDetailScreen(model: model, taskID: taskID)
            }
        }
    }
}

private struct TaskDetailScreen: View {
    @ObservedObject var model: AppModel
    let taskID: String
    @State private var pendingApproval: TaskStepSummary?
    @State private var showingApproval = false

    var body: some View {
        ScrollView {
            if let view = model.taskDetail, view.task.id == taskID {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(view.task.goal)
                            .font(.title2)
                        HStack {
                            Text(view.task.status.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.headline)
                            Spacer()
                            if view.task.status == "pending" {
                                Button("Run Task") {
                                    Task { await model.runTask(taskID) }
                                }
                                .disabled(model.isBusy)
                            }
                        }
                        if let failure = view.task.failure {
                            Text(failure)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                        if view.task.status == "waiting_approval" {
                            Text("Ally is paused. Review the exact step below before approving it. Approval applies only to that step ID; Ally may continue through later steps that do not require approval and will pause again before another approval-required step.")
                                .font(.callout)
                                .foregroundStyle(.secondary)
                        }
                    }

                    ForEach(view.steps) { step in
                        TaskStepCard(
                            step: step,
                            isBusy: model.isBusy,
                            approve: {
                                pendingApproval = step
                                showingApproval = true
                            },
                            retry: {
                                Task {
                                    await model.retryTaskStep(
                                        taskID: taskID,
                                        stepID: step.id
                                    )
                                }
                            }
                        )
                    }
                }
                .padding()
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 240)
            }
        }
        .navigationTitle("Task")
        .task(id: taskID) {
            await model.selectTask(taskID)
        }
        .alert(
            "Approve this exact task step?",
            isPresented: $showingApproval,
            presenting: pendingApproval
        ) { step in
            Button("Cancel", role: .cancel) {}
            Button("Approve & Continue") {
                Task {
                    await model.approveTaskStep(
                        taskID: taskID,
                        stepID: step.id
                    )
                }
            }
        } message: { step in
            Text("Tool: \(step.toolName)\nStep ID: \(step.id)\n\nOnly this step is approved. Review its arguments before continuing.")
        }
    }
}

private struct TaskStepCard: View {
    let step: TaskStepSummary
    let isBusy: Bool
    let approve: () -> Void
    let retry: () -> Void

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    Text(step.toolName)
                        .font(.headline)
                    Spacer()
                    Text(step.status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                LabeledContent("Step", value: String(step.position + 1))
                LabeledContent("Attempts", value: String(step.attempts))

                VStack(alignment: .leading, spacing: 4) {
                    Text("Arguments")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(step.argumentsText)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                if let output = step.lastOutput {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Last output")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(output.displayText)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                    }
                }

                if let error = step.lastError {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Last error")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(error)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                    }
                }

                if step.status == "approval_required" {
                    Button("Review & Approve This Step") {
                        approve()
                    }
                    .disabled(isBusy)
                } else if step.status == "failed" {
                    Button("Reset Failed Step for Retry") {
                        retry()
                    }
                    .disabled(isBusy)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(4)
        } label: {
            Text("Step \(step.position + 1)")
        }
    }
}

private struct SystemScreen: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Form {
            Section("Private inference") {
                LabeledContent("Status", value: model.snapshot?.runtime.state ?? "unknown")
                if let target = model.snapshot?.runtime.target {
                    LabeledContent("Model", value: target.model)
                    if let runtimeName = target.runtimeName {
                        LabeledContent("Runtime", value: runtimeName)
                    }
                }
            }

            Section("Proactive service") {
                LabeledContent(
                    "Health",
                    value: model.snapshot?.serviceHealth.report?.status ?? model.snapshot?.serviceHealth.state ?? "unknown"
                )
                ForEach(model.snapshot?.serviceHealth.report?.checks ?? []) { check in
                    LabeledContent(check.summary, value: check.severity)
                }
            }

            Section("Attention") {
                LabeledContent(
                    "Pending",
                    value: String(model.snapshot?.pendingAttention.items.count ?? 0)
                )
                LabeledContent(
                    "Recent deliveries",
                    value: String(model.snapshot?.attentionHistory.items.count ?? 0)
                )
            }
        }
        .formStyle(.grouped)
        .navigationTitle("System")
    }
}
#else
import Foundation

@main
struct AllyDesktopApp {
    static func main() {
        print("AllyDesktop requires macOS 14 or later.")
    }
}
#endif
