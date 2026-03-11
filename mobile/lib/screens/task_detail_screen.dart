import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../models/task.dart';
import '../services/task_service.dart';
import '../widgets/priority_badge.dart';
import '../widgets/status_chip.dart';

class TaskDetailScreen extends StatefulWidget {
  final int taskId;
  const TaskDetailScreen({super.key, required this.taskId});
  @override
  State<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  Task? _task;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final task = await TaskService.getTask(widget.taskId);
      if (mounted) setState(() { _task = task; _loading = false; });
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _updateStatus(String status) async {
    await TaskService.updateTask(widget.taskId, {'status': status});
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_task?.title ?? 'Task Detail'),
        actions: [
          if (_task != null)
            PopupMenuButton<String>(
              onSelected: (v) async {
                if (v == 'delete') {
                  final confirm = await showDialog<bool>(
                    context: context,
                    builder: (_) => AlertDialog(
                      title: const Text('Delete Task?'),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete', style: TextStyle(color: AppTheme.red))),
                      ],
                    ),
                  );
                  if (confirm == true) {
                    await TaskService.deleteTask(widget.taskId);
                    if (mounted) Navigator.pop(context);
                  }
                }
              },
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'delete', child: Text('Delete', style: TextStyle(color: AppTheme.red))),
              ],
            ),
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _task == null
          ? const Center(child: Text('Task not found'))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // Status & Priority
                Row(children: [
                  StatusChip(status: _task!.status),
                  const SizedBox(width: 8),
                  PriorityBadge(priority: _task!.priority),
                  const Spacer(),
                  if (_task!.dueDate != null)
                    Text('Due: ${_task!.dueDate!.split("T").first}', style: const TextStyle(fontSize: 12, color: AppTheme.muted)),
                ]),
                const SizedBox(height: 16),
                // Description
                if (_task!.description != null && _task!.description!.isNotEmpty) ...[
                  const Text('Description', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.muted)),
                  const SizedBox(height: 6),
                  Text(_task!.description!, style: const TextStyle(fontSize: 14, color: AppTheme.text, height: 1.5)),
                  const SizedBox(height: 16),
                ],
                // Details
                _detailRow('Assignee', _task!.assignee ?? 'Unassigned'),
                _detailRow('Category', _task!.category ?? '-'),
                _detailRow('Group', _task!.groupName ?? '-'),
                const SizedBox(height: 24),
                // Status actions
                const Text('Change Status', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.muted)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8, runSpacing: 8,
                  children: ['todo', 'in_progress', 'review', 'done'].map((s) {
                    final isActive = _task!.status == s;
                    return ElevatedButton(
                      onPressed: isActive ? null : () => _updateStatus(s),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: isActive ? AppTheme.accent : AppTheme.card,
                        foregroundColor: isActive ? Colors.white : AppTheme.text,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      ),
                      child: Text(s.replaceAll('_', ' ').toUpperCase(), style: const TextStyle(fontSize: 11)),
                    );
                  }).toList(),
                ),
              ],
            ),
    );
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        SizedBox(width: 100, child: Text(label, style: const TextStyle(fontSize: 12, color: AppTheme.muted))),
        Expanded(child: Text(value, style: const TextStyle(fontSize: 13, color: AppTheme.text))),
      ]),
    );
  }
}
