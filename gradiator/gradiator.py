#!/usr/bin/env python3

import os
import os.path
import csv
import sys
from getpass import getpass
from decimal import Decimal

from smtplib import SMTP, SMTP_SSL

import email.utils
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

class StudentsCSVFile(dict):
    def extend_lines(self, lines):
        for ln in lines:
            (title, fname, sname, title2, uname, post_addr,
             tel_no, mail_addr, jdate, stg, cmnt) = ln

            self[uname]= {'fname' : fname, 'sname' : sname, 'mail_addr' : mail_addr}

    def extend_file(self, path):
        with open(path, 'r', encoding="ISO-8859-4") as fd:
            lines= iter(csv.reader(fd, delimiter=';'))
            header= next(lines)

            self.extend_lines(lines)

class GradeFile(object):
    def __init__(self, topics, path=None):
        self.topics= topics
        self.path= path or ''

        self.task_name= os.path.basename(self.path[:-6].replace('_', ' '))

    def __getitem__(self, key):
        for (t, c) in self.topics:
            if t.lower() == key.lower():
                return(c)

        if key.lower() == 'task':
            return([self.task_name])

        raise(KeyError())

    def __contains__(self, key):
        try:
            self.__getitem__(key)

            return(True)
        except KeyError:
            return(False)

    def students(self):
        clean= list(s.strip() for s in self['Studenten'][0].split(','))

        return(clean)

    def points(self):
        clean= list(Decimal(s.strip()) for s in self['Punktzahl'][0].split('/'))

        return((clean[0], clean[1]))

    @staticmethod
    def from_lines(lines, path):
        topics= list()

        for l in lines:
            indent= l[0]
            stripped= (l[1:] if indent == ' ' else l).rstrip()

            if indent in ' \t\n':
                topics[-1][1].append(stripped)

            elif stripped.endswith(':'):
                topics.append((stripped[:-1], list()))

        return(GradeFile(topics, path))

    @staticmethod
    def from_file(path):
        with open(path, 'r') as fd:
            gf= GradeFile.from_lines(fd, path)

        return(gf)

class GradeCrawler(object):
    def __init__(self, basedir):
        grade_files= list()

        for (cur_dir, sub_dirs, files) in os.walk(basedir):
            for file_name in filter(lambda fn: fn.endswith('.grade'), files):
                path= os.path.join(cur_dir, file_name)

                grade_files.append(GradeFile.from_file(path))


        self.grade_files= grade_files

    def __iter__(self):
        return (iter(self.grade_files))

class CMDLine(object):
    def __init__(self):
        self.grade_files= list()

        self.starttime= email.utils.formatdate()

        self.student_map= StudentsCSVFile()

    def prepare_mail(self, tasks, nick, from_addr='', subject='', header=''):
        body_text= header
        attachments= list()

        for task_name in sorted(tasks.keys()):
            grade_file= tasks[task_name]

            body_text+= '\n\n' + task_name + '\n'
            body_text+= '#' * len(task_name) + '\n' + '\n'

            for (topic_name, topic_lines) in grade_file.topics:
                body_text+= topic_name + ':\n'

                for line in topic_lines:
                    body_text+= '  ' + line + '\n'

            if 'datei' in grade_file:
                for filename in filter(None, grade_file['datei']):
                    filepath=os.path.join(
                        os.path.dirname(grade_file.path),
                        filename
                    )

                    attachment= MIMEBase('application', 'octet-stream')

                    with open(filepath, 'rb') as fd:
                        attachment.set_payload(fd.read())

                    attachment.add_header('Content-Disposition', 'attachment', filename=filename)

                    attachments.append(attachment)

        msg= MIMEMultipart()

        msg['Subject']= subject
        msg['From']= from_addr
        msg['Date']= self.starttime
        msg['To']= email.utils.formataddr((
            self.student_map[nick]['fname'] + ' ' + self.student_map[nick]['sname'],
            self.student_map[nick]['mail_addr']
        ))

        msg.attach(MIMEText(body_text))

        for attachment in attachments:
            msg.attach(attachment)

        return(msg)

    def sorted_submissions(self):
        submissions= dict()

        for gf in self.grade_files:
            try:
                student_nicks= gf.students()
                task_name= gf['task'][0]

                for nick in student_nicks:
                    if nick not in submissions:
                        submissions[nick]= dict()

                    submissions[nick][task_name]= gf

            except Exception as e:
                print(gf.path)

                raise(e)

        return(submissions)

    def cmd_send_mails(self, argv):
        mail_cfg_file= next(argv)

        header_file= next(argv)
        subject= next(argv)

        with open(mail_cfg_file) as mcfgf:
            mcfg= iter(a.strip() for a in mcfgf)

            from_name= next(mcfg)
            from_baremail= next(mcfg)
            from_addr= email.utils.formataddr((from_name, from_baremail))

            smtp_user= next(mcfg)
            smtp_pwd= getpass()

            smtp_host= next(mcfg)
            smtp_port= int(next(mcfg))

            smtp_proto= next(mcfg)

        submissions= self.sorted_submissions()

        with open(header_file, 'r') as hffd:
            header= hffd.read()

        srv= None

        if smtp_pwd:
            if smtp_proto=='ssl':
                print(smtp_host, smtp_port)
                srv= SMTP_SSL(smtp_host, smtp_port)
            else:
                srv= SMTP(smtp_host, smtp_port)

                srv.starttls()

            srv.login(smtp_user, smtp_pwd)

        if not srv:
            os.mkdir('mails')

        for (nick, grade_files) in submissions.items():
            mail= self.prepare_mail(grade_files, nick, from_addr, subject, header)

            if srv:
                print('Sending mail to', nick, '...')
                print(srv.send_message(mail))
                print('... done.')
            else:
                mail_path= os.path.join('mails', nick + '.eml')

                with open(mail_path, 'wb') as mf:
                    mf.write(mail.as_bytes())

        if srv:
            srv.quit()

    def cmd_crawl_grades(self, argv):
        base_path= next(argv)

        self.grade_files.extend(GradeCrawler(base_path))

    def cmd_print_sum_csv(self, argv):
        submissions= self.sorted_submissions()

        print('{};"{}";{};{}'.format(
            'Kürzel', 'Vorname Nachname', 'Punktzahl erreicht', 'Punktzahl möglich'
        ))

        results= list()

        for (nick, grade_files) in submissions.items():
            points_sum= Decimal()
            points_total_sum= Decimal()

            for (task_name, grade_file) in grade_files.items():
                (points, points_total)= grade_file.points()

                points_sum+= points
                points_total_sum+= points_total

            results.append((
                nick,
                self.student_map[nick]['fname'],
                self.student_map[nick]['sname'],
                points_sum,
                points_total_sum
            ))

        results= sorted(results, key= lambda a: a[2])

        for (nick, fname, sname, psum, ptotsum) in results:
            print('{};"{}";{};{}'.format(
                nick,
                fname + ' ' + sname,
                psum,
                ptotsum
            ))

    def cmd_read_student_map(self, argv):
        map_path= next(argv)

        self.student_map.extend_file(map_path)

    def cmd_pretty_student_map(self, argv):
        lines= list()

        for (nick, info) in self.student_map.items():
            lines.append('{:35} {:12} {:15}'.format(
                info['fname'] + ' ' + info['sname'],
                nick,
                info['mail_addr']
            ))

        print('\n'.join(sorted(lines)))

    def __call__(self, argv):
        arg_iter= iter(argv)

        for cmd in arg_iter:
            fn= getattr(self, 'cmd_' + cmd)

            fn(arg_iter)

if __name__ == '__main__':
    cmd= CMDLine()

    cmd(iter(sys.argv[1:]))
