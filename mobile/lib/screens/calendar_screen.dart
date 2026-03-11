import 'package:flutter/material.dart';
import 'package:table_calendar/table_calendar.dart';
import '../config/theme.dart';
import '../services/calendar_service.dart';

class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key});
  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;
  Map<DateTime, List<Map<String, dynamic>>> _events = {};
  List<Map<String, dynamic>> _selectedEvents = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  Future<void> _loadEvents() async {
    setState(() => _loading = true);
    try {
      final start = DateTime(_focusedDay.year, _focusedDay.month, 1);
      final end = DateTime(_focusedDay.year, _focusedDay.month + 1, 0, 23, 59);
      final events = await CalendarService.getEvents(
        timeMin: start.toIso8601String(),
        timeMax: end.toIso8601String(),
      );
      final map = <DateTime, List<Map<String, dynamic>>>{};
      for (final e in events) {
        final dateStr = e['start']?['dateTime'] ?? e['start']?['date'] ?? '';
        if (dateStr.isNotEmpty) {
          final date = DateTime.tryParse(dateStr);
          if (date != null) {
            final key = DateTime(date.year, date.month, date.day);
            map.putIfAbsent(key, () => []).add(e);
          }
        }
      }
      if (mounted) setState(() { _events = map; _loading = false; });
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<Map<String, dynamic>> _getEventsForDay(DateTime day) {
    return _events[DateTime(day.year, day.month, day.day)] ?? [];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Calendar')),
      body: Column(
        children: [
          TableCalendar(
            firstDay: DateTime(2024), lastDay: DateTime(2028),
            focusedDay: _focusedDay,
            selectedDayPredicate: (d) => isSameDay(_selectedDay, d),
            eventLoader: _getEventsForDay,
            onDaySelected: (selected, focused) {
              setState(() { _selectedDay = selected; _focusedDay = focused; _selectedEvents = _getEventsForDay(selected); });
            },
            onPageChanged: (focused) { _focusedDay = focused; _loadEvents(); },
            calendarStyle: CalendarStyle(
              defaultTextStyle: const TextStyle(color: AppTheme.text),
              weekendTextStyle: const TextStyle(color: AppTheme.muted),
              outsideTextStyle: TextStyle(color: AppTheme.muted.withOpacity(0.5)),
              todayDecoration: BoxDecoration(color: AppTheme.accent.withOpacity(0.3), shape: BoxShape.circle),
              selectedDecoration: const BoxDecoration(color: AppTheme.accent, shape: BoxShape.circle),
              markerDecoration: const BoxDecoration(color: AppTheme.orange, shape: BoxShape.circle),
              markerSize: 6,
            ),
            headerStyle: const HeaderStyle(
              formatButtonVisible: false,
              titleTextStyle: TextStyle(color: AppTheme.text, fontSize: 16, fontWeight: FontWeight.w600),
              leftChevronIcon: Icon(Icons.chevron_left, color: AppTheme.muted),
              rightChevronIcon: Icon(Icons.chevron_right, color: AppTheme.muted),
            ),
            daysOfWeekStyle: const DaysOfWeekStyle(
              weekdayStyle: TextStyle(color: AppTheme.muted, fontSize: 12),
              weekendStyle: TextStyle(color: AppTheme.muted, fontSize: 12),
            ),
          ),
          const Divider(color: AppTheme.border, height: 1),
          Expanded(
            child: _selectedEvents.isEmpty
              ? const Center(child: Text('No events for this day', style: TextStyle(color: AppTheme.muted)))
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _selectedEvents.length,
                  itemBuilder: (_, i) {
                    final e = _selectedEvents[i];
                    final time = (e['start']?['dateTime'] ?? '').toString();
                    final timeStr = time.length >= 16 ? time.substring(11, 16) : 'All day';
                    return Card(
                      child: ListTile(
                        leading: Container(
                          width: 4, height: 40,
                          decoration: BoxDecoration(color: AppTheme.accent, borderRadius: BorderRadius.circular(2)),
                        ),
                        title: Text(e['summary'] ?? 'No title', style: const TextStyle(fontSize: 14, color: AppTheme.text)),
                        subtitle: Text(timeStr, style: const TextStyle(fontSize: 12, color: AppTheme.muted)),
                      ),
                    );
                  },
                ),
          ),
        ],
      ),
    );
  }
}
