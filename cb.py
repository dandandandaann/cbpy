#!/usr/bin/env python3

import argparse
import os
import subprocess
import ctypes
import sys
from multiprocessing import Process

class Project:
  def __init__(self, filepath, command):
    self.filepath = filepath
    self.command = command

# TODO: load this from a json config file
# This is where you configure your server filepath with its start command.
# Most servers use the `./start_server.ps1` command.
projectMap = {
#    "azurite" : Project("../", "run_azurite.ps1"),
    "ape" : Project("end-ape/APE/", "start_server.ps1"),
    "api" : Project("end-api/Endor.Api.Web/", "start_server.ps1"),
    "ate" : Project("end-ate/ATE/", "start_server.ps1"),
    "auth" : Project("end-auth/Endor.Auth.Web/", "start_server.ps1"),
    "boardapi" : Project("end-boardapi/Endor.BoardApi.Web/", "start_server.ps1"),
    "common" : None,
    "integrations" : Project("end-integrations/src/CoreBridge.Integrations.Web", "start_server.ps1"),
    "logging" : Project("end-logging/Endor.Logging.Web/", "start_server.ps1"),
    "comms" : Project("end-comms/src/Endor.Comm.Web/", "start_server.ps1"),
    "reporting" : Project("end-reporting/src/Endor.Reporting.Web/", "start_server.ps1"),
    "rtc" : Project("end-rtc/Endor.RTC.Core.Web/", "start_server.ps1"),
    "rtcpeerhost" : Project("end-rtcpeerhost/Endor.RTC.PeerHost.Web/",  "start_server.ps1"),
    "search" : Project("end-search-core/Endor.Search.Web/", "start_server.ps1"),
    "tasks" : Project("end-tasks/src/Endor.Tasks.Web/", "start_server.ps1"),
    "web" : Project("end-web/", "npm start")
}

parser = argparse.ArgumentParser(description="Tool to work with ENDOR.")
parser.add_argument("-a", "--azurite", help="run azurite", action="store_true")
parser.add_argument("-b", "--branch", type=str, help="create the branch")
parser.add_argument("-c", "--checkout", type=str, nargs="+", help="the target branch to checkout")
parser.add_argument("-d", "--defaultbranch", type=str, default="dev", nargs="?", help="specify branch to checkout when --checkout branch is not found")
parser.add_argument("-e", "--exportbacpac", type=str, help="run export DB bacpac script")
parser.add_argument("-i", "--npmi", help="run npm i command on end-web", action="store_true")
parser.add_argument("-m", "--merge", type=str, help="merge branch")
parser.add_argument("-p", "--path", type=str, default=os.getcwd(), help="directory that contains all target repositories")
parser.add_argument("-s", "--start", type=str, nargs="*", help="whether or nor the servers will start. False by default", choices=list(projectMap.keys()))
parser.add_argument("-S", "--status", help="shows git status of repos", action="store_true")
parser.add_argument("-u", "--undochanges", help="undo local changes with 'git reset --hard' before checkout", action="store_true")
parser.add_argument("-x", "--stash", help="will run git stash on every repo", action="store_true")
parser.add_argument("-v", "--verbose", help="show logs when executing", action="store_true")
parser.add_argument("-dry", "--dry-run", help="Test script by printing commands instead of executing them", action="store_true")
# new commands
parser.add_argument("-git", "--gitcommand", type=str, nargs="+", help="run git command on selected projects. use _ instead of - for compatibility eg: py cb.py -git 'merge __no_ff END-12345' web api")
parser.add_argument("-pw", "--powershell", type=str, nargs="+", help="run powershell command on selected projects. use _ instead of - for compatibility eg: py cb.py -pw '\\\"Current folder: $(Split-Path _Path (Get-Location) _Leaf)\\\"' web api")
parser.add_argument("-ef", "--dotnet-ef", type=str, nargs="+", help="execute dotnet ef to 'add' or 'update' migrations from Endor.EF eg: py -ef add END-54321_Drop_BusinessDB1 ")
parser.add_argument("-r", "--restore", help="restore nuget packages in every project (you need nuget.exe CLI added to your PATH for this command to work)", action="store_true")
parser.add_argument("-hosts", "--open-hosts", action="store_true", help="open windows hosts file in notepad")
# future commands
# parser.add_argument("-nu", "--nugetupdate", type=str, help="run dotnet add and dotnet restore for the selected project in its dependents eg: py cb.py -nu Endor.Model")

verbose = False
dryrun = False

summary = {}

def IsNewCommand(args):
    return args.gitcommand is not None or args.powershell is not None or args.dotnet_ef  is not None or args.restore == True or args.open_hosts == True

def log(log_entry, force = False):
    if verbose or force:
        print(f"{log_entry}")

def logWithSeparator(log_entry, separator = '-', start = 20, end = 35, force = False):
    log((separator * start) + f" {log_entry} " + (separator * (end - len(log_entry))), force)

def good(log_entry):
    logWithSeparator(f"GOOD :: {log_entry}", '=', 5, 50)

def warn(log_entry, force = False):
    logWithSeparator(f"WARN :: {log_entry}", '=', 5, 50, force)

def fail(log_entry, fatalError = False):
    log(f"FAIL :: {log_entry}", True)
    if fatalError:
        sys.exit()

# convenience function os.path.isdir
def dir_exists(path):
    return os.path.isdir(path)

# convenience function for os.path.isfile
def file_exists(path):
    return os.path.isfile(path)

# returns true if a file should be ignored
def ignore(path):
    return "." in path

def valid_branch(branch):
    if branch == None:
        return False
    branchInputed = [i for i in branch if i not in projectMap.keys()] # filter branch name in the arguments
    if(len(branch) >= 1 and len(branchInputed) < 1):
        fail(f"Error: Type one branch name to use checkout.")
        return False
    if(len(branchInputed) > 1):
        fail(f"Error: Type only one branch name to use checkout. Inputed branches: {branchInputed}")
        return False
    return len(branch) > 0

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# run and popen are the only methods that execute commands
# this method should not be used directly as it doesn't account for --verbose
def run(command):
    if not dryrun:
        out = ''
        try:
            out = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as outEx:
            out = outEx.output
        fullOutput = out.decode()
        if verbose:
            print(fullOutput)

        return fullOutput

def popen(command, exe = 'powershell.exe'): # TODO: load powershell.exe from json config file
    if dryrun or verbose:
        print(f'{exe} {command}')
    if not dryrun:
        subprocess.Popen([exe, command])

def git(command):
    if verbose:
        print(f"$ git {command}")
    return run(f"git {command}")

def execute(command):
    if verbose:
        print(f"> {command}")
    return run(command)

def checkout(branch, dir, path, defaultBranch = "dev", undoChanges = False, isVerbose = False):
    global verbose
    verbose = isVerbose
    try:
        os.chdir(os.path.join(path, dir))
    except PermissionError:
        fail(f"{dir} :: Access denied")
        return

    good(f"{dir} CHECKOUT {branch}")

    if dir == "end-web" or dir == "end-ape":
        git("checkout *npm-shrinkwrap.json")
    if undoChanges:
        git("reset --hard")

    checkoutLog = git(f"checkout {defaultBranch}")
    
    # error: Your local changes to the following files would be overwritten by checkout:
    #         Endor.Api.Web/Classes/Request/PaymentRequest.cs
    # Please commit your changes or stash them before you switch branches.
    # Aborting

    if checkoutLog and "local changes to the following files would be overwritten by checkout" in checkoutLog:
        warn(checkoutLog, True)
        return

    git("pull")

    if branch != defaultBranch:
        git(f"checkout {branch}")
        git("rebase")

def main(args):
    try:
        os.chdir(args.path)
    except FileNotFoundError:
        fail(f"Error: {args.path} is not a valid path.")
        return

    if  (args.branch is None and args.checkout is None and args.exportbacpac is None and args.npmi == False and args.merge is None and
        args.start is None and args.status == False and args.undochanges == False and args.stash == False and args.gitcommand is None and
        args.powershell is None and args.dotnet_ef is None and args.open_hosts == False and args.restore == False):
        parser.print_help()
        return
    
    global verbose
    global dryrun
    global summary

    if IsNewCommand(args):
        args.verbose = True

    verbose = args.verbose
    if args.dry_run:
        verbose = True
        dryrun = True

    singleQuote = '\''

    checkout_threads = []
    repos_found = False
    validDirs = list(filter(lambda x: dir_exists(x) and not ignore(x), os.listdir(args.path)))
        
    if valid_branch(args.checkout):
        args.status = True # force --status to creat summary
        branchInputed = [i for i in args.checkout if i not in projectMap.keys()] # filter branch name in the arguments
        print(validDirs)

        for dir in validDirs:
            if(len(args.checkout) > 1 and dir.split('-', 1)[-1] not in args.checkout): # check if current project was not selected
                continue
            if dryrun:
                checkout(branchInputed[0], dir, args.path, args.defaultbranch, args.undochanges, verbose)
            else:
                #thread = threading.Thread(target=checkout, args=(branchInputed[0], dir, args.path))
                thread = Process(target=checkout, args=(branchInputed[0], dir, args.path, args.defaultbranch, args.undochanges, verbose))
                checkout_threads.append(thread)
                thread.start()

    # wait checkout threads
    for thread in checkout_threads:
        thread.join()

    for dir in validDirs:
        repos_found = True
        currentProject = dir.split('-', 1)[-1]
        try:
            os.chdir(os.path.join(args.path, dir))
        except PermissionError:
            fail(f"{dir} :: Access denied")
            continue

        logWithSeparator(dir)

        if args.powershell and currentProject in args.powershell:
            joinedArgs = ' '.join(args.powershell)
            if joinedArgs.count(singleQuote) < 2:
                fail('Error: typed powershell command must be in single quotes', True)

            pwCommand = joinedArgs[joinedArgs.index(singleQuote) + 1:joinedArgs.rindex(singleQuote)]

            if currentProject in joinedArgs.replace(pwCommand, ''):
                popen(pwCommand.replace('_', '-'))

        if args.gitcommand and currentProject in args.gitcommand:
            joinedArgs = ' '.join(args.gitcommand)
            if joinedArgs.count(singleQuote) < 2:
                fail('Error: typed git command must be in single quotes', True)

            gitCommand = joinedArgs[joinedArgs.index(singleQuote) + 1:joinedArgs.rindex(singleQuote)]

            if currentProject in joinedArgs.replace(gitCommand, ''):
                git(gitCommand.replace('_', '-'))

        if args.stash:
            good(f"{dir} STASH")
            git("stash")

        
        if args.status:
            output = git("status")
            if output:
                currentBranch = output.split('\n')[0].split(' ')[2]
                branchKey = 'Branch ' + currentBranch
                if branchKey not in summary:
                    summary[branchKey] = ''
                summary[branchKey] += dir + ', '

                notStagedMessage = "Changes not staged"

                if notStagedMessage in output:
                    outputLines = output.split('\n')
                    notStaged = ''
                    for line in range(len(outputLines)):
                        if notStagedMessage in outputLines[line]: # start populating notStaged
                            notStaged = '\n' + (' ' * 5) + outputLines[line]
                        elif notStaged: # keep populating notStaged
                            if len(outputLines[line].strip()) == 0: # stop populating when emptyline
                                break
                            elif outputLines[line].strip().startswith('('): # ignore help lines
                                continue
                            notStaged += '\n' + (' ' * 7) + outputLines[line]
                    summary[f'{notStagedMessage} in {dir}'] = notStaged

        if args.merge:
            git(f"merge --no-ff {args.merge}")
        elif valid_branch(args.branch):
            git(f"checkout {defaultBranch}")
            git("pull")
            git(f"checkout -b {args.branch}")
            git(f"push -u origin {args.branch}")

        if dir == "end-web" and args.npmi:
            execute(f"npm i")

        if dir == "end-common" and args.dotnet_ef:
            os.chdir(os.path.join(args.path, dir, "Endor.EF"))
            if args.dotnet_ef[0] == "update":
                execute("dotnet ef database update -s ..\\Endor.EF.StartupEmulator\\Endor.EF.StartupEmulator.csproj");
            elif args.dotnet_ef[0] == "add":
                execute(f"dotnet ef migrations {' '.join(args.dotnet_ef)} -s ..\\Endor.EF.StartupEmulator\\Endor.EF.StartupEmulator.csproj")

        if args.restore and dir not in ["end-web"]:
            if dir == "end-common":
                execute(f'dotnet restore "Endor.Common.Level1.sln" --configfile "%AppData%/NuGet/NuGet.Config"');
                execute(f'dotnet restore "Endor.Common.Level2.sln" --configfile "%AppData%/NuGet/NuGet.Config"');
            else:
                execute(f'dotnet restore --configfile "%AppData%/NuGet/NuGet.Config"');

    # for dir in validDirs: END

    if not repos_found:
        warn(f"Error: No repositories found in {args.path}")

    # populate with every project if --start have no argument
    if args.start == []:
        args.start = list((project for project in projectMap.keys() if projectMap[project] != None))

    if args.start:
        for item in args.start:
            good(f"{item} starting...")
            try:
                os.chdir(os.path.join(args.path, projectMap[item].filepath))
                runCmd = "Start-Process pwsh '-NoExit -c', 'Set-Location \"{0}\"; {1}' -Verb RunAs".format(
                    os.path.join(args.path, projectMap[item].filepath),
                    (projectMap[item].command, './' + projectMap[item].command)[".ps1" in projectMap[item].command]
                )

                popen(runCmd)
            except FileNotFoundError:
                fail(f"Error: {os.path.join(args.path, projectMap[item].filepath)} is not a valid path.")
                continue
            except:
                fail(f"Error: Unknown Error starting {projectMap[item].filepath}")
                continue

    if args.exportbacpac:
        bacpacPath = 'C:/Users/*/Desktop/Corebridge/DB/' # TODO: load from json config file
        bacpacScript = f'./export_{args.exportbacpac}_bacpac.ps1'
        try:
            os.chdir(bacpacPath)
            runCmd = "pwsh '-NoExit -c', 'Set-Location \"{0}\"; {1}' -Verb RunAs".format(
                bacpacPath, bacpacScript
            )
            popen(runCmd)
        except FileNotFoundError:
            fail(f"Error: {os.path.join(bacpacPath, bacpacScript)} is not a valid path.")
        except:
            fail(f"Error: Unknown Error starting {runCmd}")
    
    if args.open_hosts:
        popen('Start-Process -Verb "runas" notepad.exe C:/Windows/System32/drivers/etc/hosts')
        # fail(f"Error: open hosts command not implemented")
        # check if running as admin?

    if summary:
        print ('Summary: ')
        for key in sorted(list(summary), key=str.casefold):
            print('  ', key, ' -> ', summary[key])

    if args.azurite:
        runCmd = "Start-Process pwsh '-c', 'azurite -s -l C:\\CoreBridge\\Azurite -d C:\\CoreBridge\\Azurite\\debug.log' -Verb RunAs"
        popen(runCmd)

    return

if __name__ == "__main__":
    main(parser.parse_args())