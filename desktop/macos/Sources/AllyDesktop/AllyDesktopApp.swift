#if os(macOS)
import SwiftUI
import AllyDesktopCore

private enum SidebarSelection: Hashable {
    case conversation(String)
    case memory
    case knowledge
    case tasks
    case attention
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
                    Label("Attention", systemImage: "bell.badge")
                        .tag(SidebarSelection.attention)
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
                case .attention:
                    AttentionScreen(model: model)
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
    @State private var searchText = ""

    private var displayedMemories: [MemorySummary] {
        searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? model.memories
            : model.memorySearchResults
    }

    var body: some View {
        NavigationStack {
            List(displayedMemories) { memory in
                NavigationLink(value: memory.id) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(memory.content)
                            .lineLimit(3)
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
            }
            .navigationTitle("Memory")
            .searchable(text: $searchText, prompt: "Search active memory")
            .onSubmit(of: .search) {
                Task { await model.searchMemories(searchText) }
            }
            .onChange(of: searchText) { _, value in
                if value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    model.memorySearchResults = []
                }
            }
            .navigationDestination(for: String.self) { memoryID in
                MemoryDetailScreen(model: model, memoryID: memoryID)
            }
        }
    }
}

private struct MemoryDetailScreen: View {
    @ObservedObject var model: AppModel
    let memoryID: String
    @State private var showingCorrection = false
    @State private var showingRetraction = false
    @State private var correctionText = ""

    var body: some View {
        ScrollView {
            if let memory = model.memoryDetail, memory.id == memoryID {
                VStack(alignment: .leading, spacing: 18) {
                    Text(memory.content)
                        .font(.title3)
                        .textSelection(.enabled)

                    GroupBox("State") {
                        VStack(alignment: .leading, spacing: 8) {
                            LabeledContent("Status", value: memoryStatus(memory))
                            LabeledContent("Kind", value: memory.kind)
                            LabeledContent("Privacy", value: memory.privacy)
                            LabeledContent(
                                "Confidence",
                                value: memory.confidence.formatted(
                                    .number.precision(.fractionLength(2))
                                )
                            )
                            LabeledContent(
                                "Importance",
                                value: memory.importance.formatted(
                                    .number.precision(.fractionLength(2))
                                )
                            )
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(4)
                    }

                    GroupBox("Provenance") {
                        VStack(alignment: .leading, spacing: 8) {
                            LabeledContent("Source type", value: memory.source.type)
                            if let sourceID = memory.source.id {
                                LabeledContent("Source ID", value: sourceID)
                            }
                            if let sourceURI = memory.source.uri {
                                LabeledContent("Source URI", value: sourceURI)
                            }
                            LabeledContent("Memory ID", value: memory.id)
                            if let supersedes = memory.supersedes {
                                LabeledContent("Corrects", value: supersedes)
                            }
                            if let supersededBy = memory.supersededBy {
                                LabeledContent("Replaced by", value: supersededBy)
                            }
                        }
                        .font(.callout)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(4)
                    }

                    if memory.isActive {
                        HStack {
                            Button("Correct Memory") {
                                correctionText = memory.content
                                showingCorrection = true
                            }
                            .disabled(model.isBusy)

                            Button("Retract Memory", role: .destructive) {
                                showingRetraction = true
                            }
                            .disabled(model.isBusy)
                        }
                    } else {
                        Text("Historical memory is preserved for provenance and is no longer used as active memory.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 240)
            }
        }
        .navigationTitle("Memory")
        .task(id: memoryID) {
            await model.selectMemory(memoryID)
        }
        .sheet(isPresented: $showingCorrection) {
            MemoryCorrectionSheet(
                content: $correctionText,
                isBusy: model.isBusy,
                cancel: { showingCorrection = false },
                save: {
                    let content = correctionText
                    showingCorrection = false
                    Task {
                        await model.correctMemory(
                            memoryID: memoryID,
                            content: content
                        )
                    }
                }
            )
        }
        .alert("Retract this memory?", isPresented: $showingRetraction) {
            Button("Cancel", role: .cancel) {}
            Button("Retract", role: .destructive) {
                Task { await model.retractMemory(memoryID) }
            }
        } message: {
            Text("The record will remain in Ally's local history for provenance, but it will no longer be active or used for retrieval.")
        }
    }

    private func memoryStatus(_ memory: MemorySummary) -> String {
        if memory.retractedAt != nil {
            return "Retracted"
        }
        if memory.supersededAt != nil {
            return "Superseded"
        }
        return "Active"
    }
}

private struct MemoryCorrectionSheet: View {
    @Binding var content: String
    let isBusy: Bool
    let cancel: () -> Void
    let save: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Correct Memory")
                .font(.title2)
            Text("Ally will preserve the original record and create this text as a new superseding memory.")
                .font(.callout)
                .foregroundStyle(.secondary)
            TextEditor(text: $content)
                .font(.body)
                .frame(minHeight: 180)
                .overlay {
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(.quaternary)
                }
            HStack {
                Spacer()
                Button("Cancel", action: cancel)
                Button("Save Correction", action: save)
                    .keyboardShortcut(.defaultAction)
                    .disabled(
                        isBusy ||
                        content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
            }
        }
        .padding()
        .frame(minWidth: 520, minHeight: 320)
    }
}

private struct KnowledgeScreen: View {
    @ObservedObject var model: AppModel
    @State private var searchText = ""
    @State private var showingIngest = false

    private var isSearching: Bool {
        !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        NavigationStack {
            List {
                if isSearching {
                    ForEach(model.knowledgeSearchResults) { hit in
                        NavigationLink(value: hit.source.id) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(hit.source.title)
                                    .font(.headline)
                                Text(hit.chunk.content)
                                    .lineLimit(4)
                                Text("score \(hit.score, format: .number.precision(.fractionLength(3)))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                } else {
                    ForEach(model.knowledge) { source in
                        NavigationLink(value: source.id) {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(source.title)
                                Text(source.uri)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
            .navigationTitle("Knowledge")
            .searchable(text: $searchText, prompt: "Search local knowledge")
            .onSubmit(of: .search) {
                Task { await model.searchKnowledge(searchText) }
            }
            .onChange(of: searchText) { _, value in
                if value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    model.knowledgeSearchResults = []
                }
            }
            .toolbar {
                ToolbarItem {
                    Button {
                        showingIngest = true
                    } label: {
                        Label("Add Note", systemImage: "plus")
                    }
                    .disabled(model.isBusy)
                }
            }
            .navigationDestination(for: String.self) { sourceID in
                KnowledgeDetailScreen(model: model, sourceID: sourceID)
            }
        }
        .sheet(isPresented: $showingIngest) {
            KnowledgeIngestSheet(
                isBusy: model.isBusy,
                cancel: { showingIngest = false },
                ingest: { title, text in
                    showingIngest = false
                    Task { await model.ingestKnowledge(title: title, text: text) }
                }
            )
        }
    }
}

private struct KnowledgeDetailScreen: View {
    @ObservedObject var model: AppModel
    let sourceID: String

    var body: some View {
        ScrollView {
            if let view = model.knowledgeDetail, view.source.id == sourceID {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(view.source.title)
                            .font(.title2)
                        Text(view.source.uri)
                            .font(.callout.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                        HStack {
                            Text(view.source.mediaType)
                            Text("revision \(view.source.currentRevision)")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }

                    GroupBox("Current content") {
                        VStack(alignment: .leading, spacing: 14) {
                            ForEach(view.currentChunks) { chunk in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Chunk \(chunk.ordinal + 1)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(chunk.content)
                                        .textSelection(.enabled)
                                }
                                if chunk.id != view.currentChunks.last?.id {
                                    Divider()
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(4)
                    }

                    GroupBox("Revision history") {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(view.revisions) { revision in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("Revision \(revision.revision)")
                                        .font(.headline)
                                    Text(revision.sha256)
                                        .font(.caption.monospaced())
                                        .foregroundStyle(.secondary)
                                        .textSelection(.enabled)
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(4)
                    }
                }
                .padding()
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 240)
            }
        }
        .navigationTitle("Knowledge Source")
        .task(id: sourceID) {
            await model.selectKnowledgeSource(sourceID)
        }
    }
}

private struct KnowledgeIngestSheet: View {
    let isBusy: Bool
    let cancel: () -> Void
    let ingest: (String, String) -> Void
    @State private var title = ""
    @State private var text = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Add Local Knowledge")
                .font(.title2)
            Text("Paste text into Ally's local knowledge store. This desktop flow does not read a filesystem path or send the text to a model.")
                .font(.callout)
                .foregroundStyle(.secondary)
            TextField("Title", text: $title)
                .textFieldStyle(.roundedBorder)
            TextEditor(text: $text)
                .frame(minHeight: 240)
                .overlay {
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(.quaternary)
                }
            HStack {
                Spacer()
                Button("Cancel", action: cancel)
                Button("Add to Knowledge") {
                    ingest(title, text)
                }
                .keyboardShortcut(.defaultAction)
                .disabled(
                    isBusy ||
                    title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                    text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                )
            }
        }
        .padding()
        .frame(minWidth: 620, minHeight: 440)
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

private struct AttentionScreen: View {
    @ObservedObject var model: AppModel
    @State private var mode = "Events"
    @State private var eventFilter = "Pending"

    private var displayedEvents: [EventSummary] {
        switch eventFilter {
        case "Handled":
            return model.attentionEvents.filter { $0.handledAt != nil }
        case "All":
            return model.attentionEvents
        default:
            return model.attentionEvents.filter { $0.handledAt == nil }
        }
    }

    var body: some View {
        NavigationStack {
            List {
                Section("macOS notifications") {
                    LabeledContent(
                        "Authorization",
                        value: notificationStatus(model.notificationAuthorization)
                    )
                    if model.notificationAuthorization.canRequestAuthorization {
                        Button("Enable Notifications") {
                            Task { await model.requestNotificationAuthorization() }
                        }
                        .disabled(model.isBusy)
                    } else if model.notificationAuthorization == .denied {
                        Text("Notifications are denied for this app. Change the permission in macOS System Settings if you want visible Ally alerts.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    } else if model.notificationAuthorization.canPresentNotifications {
                        Text("The desktop app is authorized to present notifications. Durable delivery state and user-handled state remain separate inside Ally.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Notification authorization is currently unavailable or unrecognized. Ally's durable attention history remains local and inspectable.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    Picker("View", selection: $mode) {
                        Text("Events").tag("Events")
                        Text("Delivery History").tag("Delivery History")
                    }
                    .pickerStyle(.segmented)
                }

                if mode == "Events" {
                    Section {
                        Picker("Events", selection: $eventFilter) {
                            Text("Pending").tag("Pending")
                            Text("Handled").tag("Handled")
                            Text("All").tag("All")
                        }
                        .pickerStyle(.segmented)

                        if displayedEvents.isEmpty {
                            Text("No attention events in this view.")
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(displayedEvents) { event in
                                NavigationLink(value: event.id) {
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(event.displayText)
                                            .lineLimit(3)
                                        HStack(spacing: 8) {
                                            Text(event.attention.replacingOccurrences(of: "_", with: " ").capitalized)
                                            Text(event.importance.capitalized)
                                            Text(event.handledAt == nil ? "Pending" : "Handled")
                                        }
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    }
                                    .padding(.vertical, 4)
                                }
                            }
                        }
                    } header: {
                        Text("Attention events")
                    } footer: {
                        Text("A delivered notification is not the same as a handled event. Ally only marks an event handled after an explicit local action.")
                    }
                } else {
                    Section("Delivery history") {
                        if model.attentionDeliveryHistory.isEmpty {
                            Text("No delivery attempts recorded.")
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(model.attentionDeliveryHistory) { delivery in
                                NavigationLink(value: delivery.eventId) {
                                    VStack(alignment: .leading, spacing: 5) {
                                        HStack {
                                            Text(delivery.sinkId)
                                                .font(.headline)
                                            Spacer()
                                            Text(delivery.status.capitalized)
                                        }
                                        Text("Attempts: \(delivery.attempts)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        if let error = delivery.lastError {
                                            Text(error)
                                                .font(.caption.monospaced())
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    .padding(.vertical, 4)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Attention")
            .navigationDestination(for: String.self) { eventID in
                AttentionDetailScreen(model: model, eventID: eventID)
            }
            .task {
                await model.refreshAttention()
                await model.refreshNotificationAuthorization()
            }
        }
    }

    private func notificationStatus(
        _ state: DesktopNotificationAuthorizationState
    ) -> String {
        switch state {
        case .authorized:
            return "Authorized"
        case .denied:
            return "Denied"
        case .notDetermined:
            return "Not Determined"
        case .provisional:
            return "Provisional"
        case .unknown:
            return "Unknown"
        }
    }
}

private struct AttentionDetailScreen: View {
    @ObservedObject var model: AppModel
    let eventID: String
    @State private var showingHandledConfirmation = false

    var body: some View {
        ScrollView {
            if let detail = model.attentionDetail, detail.event.id == eventID {
                VStack(alignment: .leading, spacing: 18) {
                    Text(detail.event.displayText)
                        .font(.title2)
                        .textSelection(.enabled)

                    GroupBox("Event") {
                        VStack(alignment: .leading, spacing: 8) {
                            LabeledContent("Type", value: detail.event.type)
                            LabeledContent("Source", value: detail.event.source)
                            LabeledContent("Importance", value: detail.event.importance)
                            LabeledContent("Attention", value: detail.event.attention)
                            LabeledContent(
                                "State",
                                value: detail.event.handledAt == nil ? "Pending" : "Handled"
                            )
                            LabeledContent("Created", value: detail.event.createdAt)
                            if let handledAt = detail.event.handledAt {
                                LabeledContent("Handled", value: handledAt)
                            }
                            if let dedupeKey = detail.event.dedupeKey {
                                LabeledContent("Dedupe key", value: dedupeKey)
                                    .textSelection(.enabled)
                            }
                            LabeledContent("Event ID", value: detail.event.id)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(4)
                    }

                    GroupBox("Local payload") {
                        if detail.event.payload.isEmpty {
                            Text("No payload fields.")
                                .foregroundStyle(.secondary)
                        } else {
                            VStack(alignment: .leading, spacing: 8) {
                                ForEach(detail.event.payload.keys.sorted(), id: \.self) { key in
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(key)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text(detail.event.payload[key]?.displayText ?? "null")
                                            .font(.caption.monospaced())
                                            .textSelection(.enabled)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(4)
                        }
                    }

                    GroupBox("Delivery history") {
                        if detail.deliveries.isEmpty {
                            Text("No delivery attempt has been recorded for this event.")
                                .foregroundStyle(.secondary)
                        } else {
                            VStack(alignment: .leading, spacing: 12) {
                                ForEach(detail.deliveries) { delivery in
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text(delivery.sinkId)
                                                .font(.headline)
                                            Spacer()
                                            Text(delivery.status.capitalized)
                                        }
                                        LabeledContent("Attempts", value: String(delivery.attempts))
                                        LabeledContent("Updated", value: delivery.updatedAt)
                                        if let deliveredAt = delivery.deliveredAt {
                                            LabeledContent("Delivered", value: deliveredAt)
                                        }
                                        if let error = delivery.lastError {
                                            LabeledContent("Safe error", value: error)
                                        }
                                    }
                                    .padding(.vertical, 4)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(4)
                        }
                    }

                    if detail.event.handledAt == nil {
                        Button("Mark Handled") {
                            showingHandledConfirmation = true
                        }
                        .disabled(model.isBusy)
                    } else {
                        Text("This event is handled. Delivery records remain preserved for provenance.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 240)
            }
        }
        .navigationTitle("Attention Detail")
        .task(id: eventID) {
            await model.selectAttention(eventID)
        }
        .alert(
            "Mark this event handled?",
            isPresented: $showingHandledConfirmation
        ) {
            Button("Cancel", role: .cancel) {}
            Button("Mark Handled") {
                Task { await model.markAttentionHandled(eventID) }
            }
        } message: {
            Text("This changes only Ally's local handled state. It does not delete the event or its delivery history.")
        }
    }
}

private struct SystemScreen: View {
    @ObservedObject var model: AppModel
    @State private var pendingProfile: RuntimeProfileSummary?
    @State private var showingProfileSelection = false

    var body: some View {
        Form {
            Section("Private inference") {
                LabeledContent("Status", value: model.snapshot?.runtime.state ?? "unknown")
                if let target = model.snapshot?.runtime.target {
                    LabeledContent("Model", value: target.model)
                    if let runtimeName = target.runtimeName {
                        LabeledContent("Runtime", value: runtimeName)
                    }
                    if let runtimeVersion = target.runtimeVersion {
                        LabeledContent("Runtime version", value: runtimeVersion)
                    }
                    if let profileID = target.profileId {
                        LabeledContent("Validated profile", value: shortHash(profileID))
                    }
                } else {
                    Text("Private inference stays unavailable until an installed validated profile is selected.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }

            Section("Validated runtime profiles") {
                let profiles = model.runtimeProfiles?.items ?? []
                if profiles.isEmpty {
                    Text("No validated profiles are installed yet. New profiles must come from Ally's qualification and install workflow; this app cannot create an arbitrary model or endpoint.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(profiles) { profile in
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(profile.model)
                                        .font(.headline)
                                    Text("\(profile.runtimeName) \(profile.runtimeVersion)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if profile.active {
                                    Label("Active", systemImage: "checkmark.seal.fill")
                                        .font(.caption)
                                }
                            }

                            HStack(spacing: 10) {
                                if let chip = profile.appleChip {
                                    Text(chip)
                                }
                                if let context = profile.contextLength {
                                    Text("context \(context)")
                                }
                                if let speed = profile.generationTokensPerSecond {
                                    Text("\(speed, format: .number.precision(.fractionLength(1))) tok/s")
                                }
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)

                            LabeledContent("Profile ID", value: shortHash(profile.profileId))
                                .font(.caption)
                                .textSelection(.enabled)

                            DisclosureGroup("Qualification evidence") {
                                VStack(alignment: .leading, spacing: 6) {
                                    evidenceRow(
                                        label: "Capability",
                                        name: profile.capabilityEvidenceName,
                                        sha256: profile.capabilityEvidenceSha256
                                    )
                                    evidenceRow(
                                        label: "Privacy",
                                        name: profile.privacyEvidenceName,
                                        sha256: profile.privacyEvidenceSha256
                                    )
                                    evidenceRow(
                                        label: "Workflows",
                                        name: profile.workflowEvidenceName,
                                        sha256: profile.workflowEvidenceSha256
                                    )
                                }
                                .padding(.top, 6)
                            }

                            if profile.active {
                                Button("Deselect Profile") {
                                    Task { await model.deselectRuntimeProfile() }
                                }
                                .disabled(model.isBusy)
                            } else {
                                Button("Select for Private Inference") {
                                    pendingProfile = profile
                                    showingProfileSelection = true
                                }
                                .disabled(model.isBusy)
                            }
                        }
                        .padding(.vertical, 6)
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
                LabeledContent(
                    "Background activity",
                    value: backgroundServiceStatus(model.backgroundServiceState)
                )
                if let lastCycle = model.lastProactiveCycleAt {
                    LabeledContent(
                        "Last local cycle",
                        value: lastCycle.formatted(
                            date: .abbreviated,
                            time: .standard
                        )
                    )
                }
                if let cycleError = model.proactiveCycleError {
                    Text(cycleError)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }

                switch model.backgroundServiceState {
                case .enabled:
                    Button("Disable Background Proactivity") {
                        model.disableBackgroundService()
                    }
                    Text("Ally is registered as the main app login item. While the app process is running, the signed app owns proactive cycles and modern notification delivery.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                case .requiresApproval:
                    Button("Open Login Items Settings") {
                        model.openBackgroundServiceSettings()
                    }
                    Text("macOS requires your approval before Ally may run at login.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                case .notRegistered, .notFound:
                    Button("Enable Background Proactivity") {
                        Task { await model.enableBackgroundService() }
                    }
                    Text("This explicitly registers the signed Ally app to launch at login. It does not install a separate desktop launch agent.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                case .unknown:
                    Button("Refresh Background Status") {
                        model.refreshBackgroundServiceState()
                    }
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
        .task {
            model.refreshBackgroundServiceState()
        }
        .alert(
            "Use this validated profile?",
            isPresented: $showingProfileSelection,
            presenting: pendingProfile
        ) { profile in
            Button("Cancel", role: .cancel) {}
            Button("Select Profile") {
                Task { await model.selectRuntimeProfile(profile.profileId) }
            }
        } message: { profile in
            Text("Private inference will use \(profile.model) through \(profile.runtimeName) \(profile.runtimeVersion). Only this already-installed evidence-backed profile ID will be selected.")
        }
    }

    @ViewBuilder
    private func evidenceRow(label: String, name: String, sha256: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(label): \(name)")
                .font(.caption)
            Text(sha256)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
    }

    private func shortHash(_ value: String) -> String {
        String(value.prefix(12))
    }

    private func backgroundServiceStatus(
        _ state: DesktopBackgroundServiceState
    ) -> String {
        switch state {
        case .enabled:
            return "Enabled"
        case .notRegistered:
            return "Not Registered"
        case .requiresApproval:
            return "Requires Approval"
        case .notFound:
            return "Not Registered"
        case .unknown:
            return "Unknown"
        }
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
