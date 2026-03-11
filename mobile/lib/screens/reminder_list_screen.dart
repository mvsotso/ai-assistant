import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';
import '../config/theme.dart';
import '../models/reminder.dart';
import '../services/reminder_service.dart';
import 'reminder_create_screen.dart';

class ReminderListScreen extends StatefulWidget {
  const ReminderListScreen({super.key});
  @override
  State<ReminderListScreen> createState() => _ReminderListScreenState();
}

class _ReminderListScreenState extends State<ReminderListScreen> {
  List<Reminder> _reminders = [];
  bool _loading = true;
  bool _showHistory = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final list = _showHistory
          ? await ReminderService.getHistory()
          : await ReminderService.getReminders();
      if (mounted) setState(() { _reminders = list; _loading = false; });
    } catch (e) {
      debugPrint('Reminder load error: $e');
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _snooze(int id, int minutes) async {
    try {
      await ReminderService.snooze(id, minutes);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Snoozed ${minutes >= 1440 ? "1 day" : "$minutes min"}')),
      );
      _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    }
  }

  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete Reminder?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete', style: TextStyle(color: AppTheme.red))),
        ],
      ),
    );
    if (confirm == true) {
      await ReminderService.delete(id);
      _load();
    }
  }

  String _formatTime(String? iso) {
    if (iso == null) return '';
    try {
      final dt = DateTime.parse(iso).toLocal();
      return DateFormat('MMM d, yyyy h:mm a').format(dt);
    } catch (_) {
      return iso;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Reminders'),
        actions: [
          TextButton(
            onPressed: () { setState(() => _showHistory = !_showHistory); _load(); },
            child: Text(_showHistory ? 'Pending' : 'History',
              style: const TextStyle(fontSize: 12, color: AppTheme.accent)),
          ),
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : RefreshIndicator(
            onRefresh: _load,
            child: _reminders.isEmpty
              ? ListView(children: [
                  SizedBox(height: MediaQuery.of(context).size.height * 0.3),
                  Center(child: Column(children: [
                    Icon(_showHistory ? Icons.history : Icons.notifications_none,
                      size: 48, color: AppTheme.muted),
                    const SizedBox(height: 12),
                    Text(_showHistory ? 'No reminder history' : 'No pending reminders',
                      style: const TextStyle(color: AppTheme.muted)),
                  ])),
                ])
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _reminders.length,
                  itemBuilder: (_, i) => _reminderCard(_reminders[i]),
                ),
          ),
      floatingActionButton: _showHistory ? null : FloatingActionButton(
        onPressed: () async {
          await Navigator.push(context,
            MaterialPageRoute(builder: (_) => const ReminderCreateScreen()));
          _load();
        },
        backgroundColor: AppTheme.accent,
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _reminderCard(Reminder r) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(r.isRecurring ? Icons.repeat : Icons.notifications_active,
              size: 16, color: r.isSent ? AppTheme.muted : AppTheme.accent),
            const SizedBox(width: 8),
            Expanded(child: Text(r.message,
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500,
                color: r.isSent ? AppTheme.muted : AppTheme.text))),
            if (r.snoozeCount > 0)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.orange.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text('Snoozed ${r.snoozeCount}x',
                  style: const TextStyle(fontSize: 9, color: AppTheme.orange)),
              ),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            const Icon(Icons.schedule, size: 12, color: AppTheme.muted),
            const SizedBox(width: 4),
            Text(_formatTime(r.remindAt),
              style: const TextStyle(fontSize: 11, color: AppTheme.muted)),
            if (r.taskTitle != null) ...[
              const SizedBox(width: 10),
              const Icon(Icons.link, size: 12, color: AppTheme.blue),
              const SizedBox(width: 3),
              Expanded(child: Text(r.taskTitle!,
                style: const TextStyle(fontSize: 11, color: AppTheme.blue),
                overflow: TextOverflow.ellipsis)),
            ],
          ]),
          if (!_showHistory && !r.isSent) ...[
            const SizedBox(height: 10),
            Row(children: [
              _snoozeBtn('15m', () => _snooze(r.id, 15)),
              const SizedBox(width: 6),
              _snoozeBtn('1h', () => _snooze(r.id, 60)),
              const SizedBox(width: 6),
              _snoozeBtn('Tomorrow', () => _snooze(r.id, 1440)),
              const Spacer(),
              InkWell(
                onTap: () => _delete(r.id),
                child: const Icon(Icons.delete_outline, size: 18, color: AppTheme.red),
              ),
            ]),
          ],
        ],
      ),
    );
  }

  Widget _snoozeBtn(String label, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: AppTheme.surface,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: AppTheme.border),
        ),
        child: Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.accent)),
      ),
    );
  }
}
