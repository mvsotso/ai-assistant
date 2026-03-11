import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../services/ai_service.dart';

class AIChatScreen extends StatefulWidget {
  const AIChatScreen({super.key});
  @override
  State<AIChatScreen> createState() => _AIChatScreenState();
}

class _AIChatScreenState extends State<AIChatScreen> {
  final _ctrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<Map<String, String>> _messages = [];
  bool _loading = false;

  Future<void> _send() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty || _loading) return;
    _ctrl.clear();
    setState(() {
      _messages.add({'role': 'user', 'content': text});
      _loading = true;
    });
    _scrollToBottom();
    try {
      final result = await AIService.chat(text, history: _messages.length > 1 ? _messages.sublist(0, _messages.length - 1) : null);
      final response = result['response'] ?? result['content'] ?? 'No response';
      setState(() => _messages.add({'role': 'assistant', 'content': response}));
    } catch (e) {
      setState(() => _messages.add({'role': 'assistant', 'content': 'Error: $e'}));
    }
    setState(() => _loading = false);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollCtrl.hasClients) _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Chat'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: () => setState(() => _messages.clear())),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: _messages.isEmpty
              ? const Center(child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.smart_toy, size: 48, color: AppTheme.muted),
                    SizedBox(height: 12),
                    Text('Ask me anything!', style: TextStyle(color: AppTheme.muted, fontSize: 16)),
                    SizedBox(height: 4),
                    Text('I can help with tasks, calendar, and more', style: TextStyle(color: AppTheme.muted, fontSize: 12)),
                  ],
                ))
              : ListView.builder(
                  controller: _scrollCtrl,
                  padding: const EdgeInsets.all(16),
                  itemCount: _messages.length + (_loading ? 1 : 0),
                  itemBuilder: (_, i) {
                    if (i == _messages.length && _loading) {
                      return const Align(alignment: Alignment.centerLeft, child: Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                      ));
                    }
                    final msg = _messages[i];
                    final isUser = msg['role'] == 'user';
                    return Align(
                      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: Container(
                        margin: const EdgeInsets.symmetric(vertical: 4),
                        padding: const EdgeInsets.all(12),
                        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
                        decoration: BoxDecoration(
                          color: isUser ? AppTheme.accent.withOpacity(0.15) : AppTheme.card,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: isUser ? AppTheme.accent.withOpacity(0.3) : AppTheme.border),
                        ),
                        child: Text(msg['content'] ?? '', style: TextStyle(fontSize: 14, color: AppTheme.text, height: 1.4)),
                      ),
                    );
                  },
                ),
          ),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: const BoxDecoration(color: AppTheme.surface, border: Border(top: BorderSide(color: AppTheme.border))),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _ctrl,
                    decoration: const InputDecoration(hintText: 'Type a message...', border: InputBorder.none, contentPadding: EdgeInsets.symmetric(horizontal: 12)),
                    style: const TextStyle(color: AppTheme.text),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                IconButton(
                  onPressed: _loading ? null : _send,
                  icon: Icon(Icons.send, color: _loading ? AppTheme.muted : AppTheme.accent),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() { _ctrl.dispose(); _scrollCtrl.dispose(); super.dispose(); }
}
