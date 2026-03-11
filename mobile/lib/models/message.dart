class ChatMessage {
  final String role;
  final String content;
  final List<dynamic>? actions;

  ChatMessage({required this.role, required this.content, this.actions});

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
    role: json['role'] ?? 'assistant',
    content: json['content'] ?? json['response'] ?? '',
    actions: json['actions'],
  );
}
