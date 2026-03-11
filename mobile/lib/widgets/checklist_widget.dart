import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../services/checklist_service.dart';

class ChecklistWidget extends StatefulWidget {
  final int taskId;
  const ChecklistWidget({super.key, required this.taskId});
  @override
  State<ChecklistWidget> createState() => _ChecklistWidgetState();
}

class _ChecklistWidgetState extends State<ChecklistWidget> {
  List<Map<String, dynamic>> _actions = [];
  int _total = 0;
  int _done = 0;
  int _progress = 0;
  bool _loading = true;
  final _newCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ChecklistService.getActions(widget.taskId);
      if (mounted) setState(() {
        _actions = List<Map<String, dynamic>>.from(data['actions'] ?? []);
        _total = data['total'] ?? 0;
        _done = data['done'] ?? 0;
        _progress = data['progress'] ?? 0;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggle(int actionId) async {
    try {
      await ChecklistService.toggleAction(widget.taskId, actionId);
      _load();
    } catch (_) {}
  }

  Future<void> _add() async {
    if (_newCtrl.text.trim().isEmpty) return;
    try {
      await ChecklistService.createAction(
          widget.taskId, {'title': _newCtrl.text.trim()});
      _newCtrl.clear();
      _load();
    } catch (_) {}
  }

  Future<void> _delete(int actionId) async {
    try {
      await ChecklistService.deleteAction(widget.taskId, actionId);
      _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const SizedBox(height: 60, child: Center(child: CircularProgressIndicator(strokeWidth: 2)));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Divider(color: AppTheme.border),
        const SizedBox(height: 8),
        // Header
        Row(children: [
          const Icon(Icons.checklist, size: 16, color: AppTheme.accent),
          const SizedBox(width: 6),
          Text('Checklist ($_done/$_total)',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.text)),
        ]),
        const SizedBox(height: 6),
        // Progress bar
        if (_total > 0)
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: _progress / 100.0,
              backgroundColor: AppTheme.surface,
              valueColor: AlwaysStoppedAnimation<Color>(
                _progress == 100 ? AppTheme.green : AppTheme.accent),
              minHeight: 5,
            ),
          ),
        const SizedBox(height: 8),
        // Action items
        ..._actions.map((a) {
          final isDone = a['is_done'] == true;
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              SizedBox(
                width: 28, height: 28,
                child: Checkbox(
                  value: isDone,
                  onChanged: (_) => _toggle(a['id']),
                  activeColor: AppTheme.accent,
                  side: const BorderSide(color: AppTheme.muted),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(child: Text(a['title'] ?? '',
                style: TextStyle(fontSize: 13,
                  color: isDone ? AppTheme.muted : AppTheme.text,
                  decoration: isDone ? TextDecoration.lineThrough : null))),
              InkWell(
                onTap: () => _delete(a['id']),
                child: const Icon(Icons.close, size: 14, color: AppTheme.muted),
              ),
            ]),
          );
        }),
        // Add new action
        const SizedBox(height: 6),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _newCtrl,
              decoration: const InputDecoration(
                hintText: 'Add checklist item...',
                hintStyle: TextStyle(fontSize: 12, color: AppTheme.muted),
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              ),
              style: const TextStyle(fontSize: 13, color: AppTheme.text),
              onSubmitted: (_) => _add(),
            ),
          ),
          const SizedBox(width: 6),
          InkWell(
            onTap: _add,
            child: Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: AppTheme.accent, borderRadius: BorderRadius.circular(6)),
              child: const Icon(Icons.add, size: 16, color: Colors.white),
            ),
          ),
        ]),
      ],
    );
  }

  @override
  void dispose() { _newCtrl.dispose(); super.dispose(); }
}
