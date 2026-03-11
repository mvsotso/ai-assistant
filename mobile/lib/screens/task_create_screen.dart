import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../services/task_service.dart';

class TaskCreateScreen extends StatefulWidget {
  const TaskCreateScreen({super.key});
  @override
  State<TaskCreateScreen> createState() => _TaskCreateScreenState();
}

class _TaskCreateScreenState extends State<TaskCreateScreen> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  String _priority = 'medium';
  String _status = 'todo';
  DateTime? _dueDate;
  bool _saving = false;

  Future<void> _save() async {
    if (_titleCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Title is required')));
      return;
    }
    setState(() => _saving = true);
    try {
      await TaskService.createTask({
        'title': _titleCtrl.text.trim(),
        'description': _descCtrl.text.trim(),
        'priority': _priority,
        'status': _status,
        if (_dueDate != null) 'due_date': _dueDate!.toIso8601String(),
      });
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
    if (mounted) setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New Task')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(controller: _titleCtrl, decoration: const InputDecoration(labelText: 'Title'), style: const TextStyle(color: AppTheme.text)),
          const SizedBox(height: 12),
          TextField(controller: _descCtrl, decoration: const InputDecoration(labelText: 'Description'), maxLines: 3, style: const TextStyle(color: AppTheme.text)),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _priority,
            decoration: const InputDecoration(labelText: 'Priority'),
            dropdownColor: AppTheme.card,
            items: ['low', 'medium', 'high', 'urgent'].map((p) =>
              DropdownMenuItem(value: p, child: Text(p.toUpperCase(), style: const TextStyle(color: AppTheme.text)))).toList(),
            onChanged: (v) => setState(() => _priority = v ?? 'medium'),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            dropdownColor: AppTheme.card,
            items: ['todo', 'in_progress', 'review', 'done'].map((s) =>
              DropdownMenuItem(value: s, child: Text(s.replaceAll('_', ' ').toUpperCase(), style: const TextStyle(color: AppTheme.text)))).toList(),
            onChanged: (v) => setState(() => _status = v ?? 'todo'),
          ),
          const SizedBox(height: 12),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(_dueDate != null ? 'Due: ${_dueDate!.toString().split(' ').first}' : 'Set Due Date',
              style: const TextStyle(fontSize: 14, color: AppTheme.text)),
            trailing: const Icon(Icons.calendar_today, color: AppTheme.muted),
            onTap: () async {
              final date = await showDatePicker(
                context: context, initialDate: DateTime.now(),
                firstDate: DateTime.now().subtract(const Duration(days: 30)),
                lastDate: DateTime.now().add(const Duration(days: 365)),
              );
              if (date != null) setState(() => _dueDate = date);
            },
          ),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Creating...' : 'Create Task'),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() { _titleCtrl.dispose(); _descCtrl.dispose(); super.dispose(); }
}
