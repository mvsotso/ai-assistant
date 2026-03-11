import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config/theme.dart';
import '../models/task.dart';
import '../services/reminder_service.dart';
import '../services/task_service.dart';

class ReminderCreateScreen extends StatefulWidget {
  const ReminderCreateScreen({super.key});
  @override
  State<ReminderCreateScreen> createState() => _ReminderCreateScreenState();
}

class _ReminderCreateScreenState extends State<ReminderCreateScreen> {
  final _msgCtrl = TextEditingController();
  DateTime? _remindAt;
  int? _quickMinutes;
  int? _linkedTaskId;
  bool _isRecurring = false;
  String _recurrenceRule = 'daily';
  bool _saving = false;
  List<Task> _tasks = [];

  @override
  void initState() {
    super.initState();
    _loadTasks();
  }

  Future<void> _loadTasks() async {
    try {
      final tasks = await TaskService.getTasks(limit: 100);
      if (mounted) setState(() => _tasks = tasks.where((t) => t.status != 'done').toList());
    } catch (_) {}
  }

  void _setQuick(int minutes) {
    setState(() {
      _quickMinutes = minutes;
      _remindAt = null;
    });
  }

  Future<void> _pickDateTime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.now().add(const Duration(hours: 1)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.now(),
    );
    if (time != null && mounted) {
      setState(() {
        _remindAt = DateTime(date.year, date.month, date.day, time.hour, time.minute);
        _quickMinutes = null;
      });
    }
  }

  Future<void> _save() async {
    if (_msgCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Message is required')));
      return;
    }
    setState(() => _saving = true);
    try {
      final body = <String, dynamic>{
        'message': _msgCtrl.text.trim(),
      };
      if (_remindAt != null) {
        body['remind_at'] = _remindAt!.toUtc().toIso8601String();
      } else if (_quickMinutes != null) {
        body['minutes'] = _quickMinutes;
      } else {
        body['minutes'] = 30; // default
      }
      if (_linkedTaskId != null) body['task_id'] = _linkedTaskId;
      if (_isRecurring) {
        body['is_recurring'] = true;
        body['recurrence_rule'] = _recurrenceRule;
      }
      await ReminderService.create(body);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
    if (mounted) setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New Reminder')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _msgCtrl,
            decoration: const InputDecoration(labelText: 'Reminder message'),
            style: const TextStyle(color: AppTheme.text),
            maxLines: 2,
          ),
          const SizedBox(height: 16),
          const Text('Quick Time', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.muted)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            _quickBtn('15 min', 15),
            _quickBtn('30 min', 30),
            _quickBtn('1 hour', 60),
            _quickBtn('2 hours', 120),
            _quickBtn('Tomorrow 9AM', 0, isTomorrow: true),
          ]),
          const SizedBox(height: 12),
          const Text('Or pick exact time:', style: TextStyle(fontSize: 12, color: AppTheme.muted)),
          const SizedBox(height: 6),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(
              _remindAt != null
                ? 'Remind at: ${DateFormat("MMM d, yyyy h:mm a").format(_remindAt!)}'
                : _quickMinutes != null
                  ? 'In $_quickMinutes minutes'
                  : 'No time set (default: 30 min)',
              style: const TextStyle(fontSize: 13, color: AppTheme.text),
            ),
            trailing: const Icon(Icons.calendar_today, color: AppTheme.muted),
            onTap: _pickDateTime,
          ),
          const SizedBox(height: 12),
          // Task link
          DropdownButtonFormField<int>(
            value: _linkedTaskId,
            decoration: const InputDecoration(labelText: 'Link to task (optional)'),
            dropdownColor: AppTheme.card,
            items: [
              const DropdownMenuItem<int>(value: null, child: Text('None', style: TextStyle(color: AppTheme.muted))),
              ..._tasks.map((t) => DropdownMenuItem<int>(
                value: t.id,
                child: Text(t.title, style: const TextStyle(color: AppTheme.text, fontSize: 13),
                  overflow: TextOverflow.ellipsis),
              )),
            ],
            onChanged: (v) => setState(() => _linkedTaskId = v),
          ),
          const SizedBox(height: 12),
          // Recurring
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Recurring', style: TextStyle(fontSize: 14, color: AppTheme.text)),
            value: _isRecurring,
            activeColor: AppTheme.accent,
            onChanged: (v) => setState(() => _isRecurring = v),
          ),
          if (_isRecurring)
            DropdownButtonFormField<String>(
              value: _recurrenceRule,
              decoration: const InputDecoration(labelText: 'Repeat'),
              dropdownColor: AppTheme.card,
              items: ['daily', 'weekly', 'monthly'].map((r) => DropdownMenuItem(
                value: r, child: Text(r[0].toUpperCase() + r.substring(1),
                  style: const TextStyle(color: AppTheme.text)))).toList(),
              onChanged: (v) => setState(() => _recurrenceRule = v ?? 'daily'),
            ),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Creating...' : 'Create Reminder'),
          ),
        ],
      ),
    );
  }

  Widget _quickBtn(String label, int minutes, {bool isTomorrow = false}) {
    final isActive = isTomorrow
        ? _quickMinutes == -1
        : _quickMinutes == minutes && !isTomorrow;
    return InkWell(
      onTap: () {
        if (isTomorrow) {
          // Calculate minutes until tomorrow 9 AM
          final now = DateTime.now();
          final tomorrow9 = DateTime(now.year, now.month, now.day + 1, 9, 0);
          final diff = tomorrow9.difference(now).inMinutes;
          setState(() {
            _quickMinutes = diff;
            _remindAt = null;
          });
        } else {
          _setQuick(minutes);
        }
      },
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? AppTheme.accent.withOpacity(0.15) : AppTheme.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: isActive ? AppTheme.accent : AppTheme.border),
        ),
        child: Text(label, style: TextStyle(fontSize: 12,
          color: isActive ? AppTheme.accent : AppTheme.text)),
      ),
    );
  }

  @override
  void dispose() { _msgCtrl.dispose(); super.dispose(); }
}
