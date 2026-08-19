; Numeric SemVer compare (major.minor.patch) and downgrade guard.
; Included by NC-Code-Generator.iss. No hardcoded app version.
; Installed version is read from the Uninstall registry key of AppId.

[Code]
function IsAllDigits(const S: String): Boolean;
var
  I: Integer;
begin
  Result := Length(S) > 0;
  for I := 1 to Length(S) do
  begin
    if (S[I] < '0') or (S[I] > '9') then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function SplitSemVer(const Version: String; var Major, Minor, Patch: Integer): Boolean;
var
  P1, P2rel, P2: Integer;
  A, B, C: String;
begin
  Result := False;
  Major := 0;
  Minor := 0;
  Patch := 0;
  P1 := Pos('.', Version);
  if P1 < 2 then
    Exit;
  P2rel := Pos('.', Copy(Version, P1 + 1, MaxInt));
  if P2rel < 2 then
    Exit;
  P2 := P1 + P2rel;
  A := Copy(Version, 1, P1 - 1);
  B := Copy(Version, P1 + 1, P2 - P1 - 1);
  C := Copy(Version, P2 + 1, MaxInt);
  if Pos('.', C) > 0 then
    Exit;
  if (not IsAllDigits(A)) or (not IsAllDigits(B)) or (not IsAllDigits(C)) then
    Exit;
  Major := StrToInt(A);
  Minor := StrToInt(B);
  Patch := StrToInt(C);
  Result := True;
end;

function CompareSemVer(const Left, Right: String): Integer;
var
  L1, L2, L3, R1, R2, R3: Integer;
begin
  { 2 = invalid / fail-closed }
  if (not SplitSemVer(Left, L1, L2, L3)) or (not SplitSemVer(Right, R1, R2, R3)) then
  begin
    Result := 2;
    Exit;
  end;
  if L1 <> R1 then
  begin
    if L1 > R1 then Result := 1 else Result := -1;
    Exit;
  end;
  if L2 <> R2 then
  begin
    if L2 > R2 then Result := 1 else Result := -1;
    Exit;
  end;
  if L3 <> R3 then
  begin
    if L3 > R3 then Result := 1 else Result := -1;
    Exit;
  end;
  Result := 0;
end;

function UninstallRegistryKey: String;
begin
  Result := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
end;

function QueryUninstallString(const ValueName: String; var Value: String): Boolean;
var
  Key: String;
begin
  Key := UninstallRegistryKey;
  Value := '';
  Result := RegQueryStringValue(HKLM, Key, ValueName, Value);
  if not Result then
    Result := RegQueryStringValue(HKCU, Key, ValueName, Value);
end;

function GetInstalledDisplayVersion: String;
var
  Value: String;
begin
  Result := '';
  if QueryUninstallString('DisplayVersion', Value) then
    Result := Value;
end;

function InitializeSetup(): Boolean;
var
  InstalledVersion: String;
  Cmp: Integer;
begin
  Result := True;
  InstalledVersion := GetInstalledDisplayVersion;
  if InstalledVersion = '' then
    Exit;

  Cmp := CompareSemVer(InstalledVersion, ExpandConstant('{#MyAppVersion}'));
  { Cmp > 0: installed is newer. Cmp = 2: unparsable installed version. }
  if (Cmp > 0) or (Cmp = 2) then
  begin
    Log('DOWNGRADE_BLOCKED installed=' + InstalledVersion + ' setup={#MyAppVersion} cmp=' + IntToStr(Cmp));
    if not WizardSilent then
      MsgBox('Eine neuere Version des NC-Code Generators ist bereits installiert.', mbError, MB_OK);
    Result := False;
  end;
end;
